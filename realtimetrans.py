import asyncio
import argparse
import os
import math

# This example uses the sounddevice library to get an audio stream from the
# microphone. It's not a dependency of the project but can be installed with
# `pip install sounddevice`.
import sounddevice

import boto3
import concurrent.futures

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent


"""
Here's an example of a custom event handler you can extend to
process the returned transcription results as needed. This
handler will simply print the text out to your interpreter.
"""

class MyEventHandler(TranscriptResultStreamHandler):
    #lastPartial = False
    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        # This handler can be implemented to handle transcriptions as needed.
        # Here's an example to get started.
        results = transcript_event.transcript.results
        for result in results:
            for alt in result.alternatives:
                columns, rows = os.get_terminal_size(0)
                txt = alt.transcript.strip()
                #os.system('echo "'+txt+'" >> a.txt')
                up = math.floor((len(txt) - 1) / columns)
                # \033[2K 擦除当前光标所在的行 \033[A 光标上移 \033[F 移动光标到上一行，列不变
                printtext = '\033[F\r' * up
                #print(txt, end='\r' if result.is_partial else '\n')
                if result.is_partial:
                    print(txt + printtext, end='\r')
                else:
                    print(txt, end='\r\n')
                    self.queue.put_nowait(txt)

async def mic_stream(args):
    # This function wraps the raw input stream from the microphone forwarding
    # the blocks to an asyncio.Queue.
    loop = asyncio.get_event_loop()
    input_queue = asyncio.Queue()

    def callback(indata, frame_count, time_info, status):
        loop.call_soon_threadsafe(input_queue.put_nowait, (bytes(indata), status))

    # Be sure to use the correct parameters for the audio stream that matches
    # the audio formats described for the source language you'll be using:
    # https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html
    stream = sounddevice.RawInputStream(
        device = args.device,
        channels = args.channels,
        samplerate = args.samplerate,
        callback = callback,
        blocksize = 1024 * 2,
        dtype = "int16",
    )
    # Initiate the audio stream and asynchronously yield the audio chunks
    # as they become available.
    with stream:
        while True:
            indata, status = await input_queue.get()
            yield indata, status


async def write_chunks(stream, args):
    # This connects the raw audio chunks generator coming from the microphone
    # and passes them along to the transcription stream.
    async for chunk, status in mic_stream(args):
        await stream.input_stream.send_audio_event(audio_chunk=chunk)
    await stream.input_stream.end_stream()

async def basic_transcribe(queue, args):
    # Setup up our client with our chosen AWS region
    client = TranscribeStreamingClient(region=args.region)

    # Start transcription to generate our async stream
    # https://github.com/awslabs/amazon-transcribe-streaming-sdk/blob/develop/amazon_transcribe/client.py
    stream = await client.start_stream_transcription(
        language_code = args.source,
        media_sample_rate_hz = args.samplerate,
        #this params must set to None
        number_of_channels = None, #args.channels,
        media_encoding="pcm",
    )

    # Instantiate our handler and start processing events
    handler = MyEventHandler(stream.output_stream)
    handler.queue = queue
    await asyncio.gather(write_chunks(stream, args), handler.handle_events())

def translate_text(client, text, args):
    ret = client.translate_text(Text=text, SourceLanguageCode=args.source, TargetLanguageCode=args.target)
    return ret

async def basic_translate(queue, args):
    translate = boto3.client(service_name="translate", region_name=args.region, use_ssl=True)
    loop = asyncio.get_event_loop()
    while True:
        transtext = await queue.get()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(pool, translate_text, translate, transtext, args)
            print(result.get('TranslatedText')+'\r\n')

async def main(args):
    queue = asyncio.Queue()
    await asyncio.wait([
        asyncio.create_task(basic_translate(queue, args)),
        asyncio.create_task(basic_transcribe(queue, args))
    ])

print('current use device list:')
print(sounddevice.query_devices())
print('')

parser = argparse.ArgumentParser()
parser.description="Realtime Translate from microphone"
parser.add_argument("-s", "--source", help="Specify input language(e.g. en-US, zh-CN, ja-JP, default: en-US)", type=str, default="en-US")
parser.add_argument("-t", "--target", help="Specify output language, default: zh-CN", type=str, default="zh-CN")
parser.add_argument("-r", "--region", help="Specify endpoint region, default: ap-northeast-1", type=str, default="ap-northeast-1")
parser.add_argument("-i", "--device", help="Specify input device, such as Soundflower can be run", type=int, default=sounddevice.default.device[0])
parser.add_argument("-sr", "--samplerate", help="Specify samplerate in HZ, default: 16000", type=int, default=16000)
args = parser.parse_args()
#channels must set to 1
args.channels = 1

print('use device:', args.device, ', channels:', args.channels ,', dtype: int16, samplerate:', args.samplerate, ', source:', args.source, ', target:', args.target, ', region:', args.region, '\r\n')
#check if params is ok
#soundflower can not support int16
sounddevice.check_input_settings(device= args.device, channels = args.channels, dtype = 'int16', samplerate = args.samplerate)

loop = asyncio.get_event_loop()
loop.run_until_complete(main(args))
loop.close()
