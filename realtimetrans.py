import asyncio
import argparse
import string

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
    queue = ''
    #lastPartial = False
    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        # This handler can be implemented to handle transcriptions as needed.
        # Here's an example to get started.
        results = transcript_event.transcript.results
        for result in results:
            for alt in result.alternatives:
                #print(alt.transcript, end='\r' if result.is_partial else '\n')
                if result.is_partial:
                    print(alt.transcript, end='\r')
                else:
                    print(alt.transcript, end='\n')
                    self.queue.put_nowait(alt.transcript)

async def mic_stream(sample_rate):
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
        channels=1,
        samplerate=sample_rate,
        callback=callback,
        blocksize=1024 * 2,
        dtype="int16",
    )
    # Initiate the audio stream and asynchronously yield the audio chunks
    # as they become available.
    with stream:
        while True:
            indata, status = await input_queue.get()
            yield indata, status


async def write_chunks(stream, sample_rate):
    # This connects the raw audio chunks generator coming from the microphone
    # and passes them along to the transcription stream.
    async for chunk, status in mic_stream(sample_rate):
        await stream.input_stream.send_audio_event(audio_chunk=chunk)
    await stream.input_stream.end_stream()

async def basic_transcribe(queue, args):
    # Setup up our client with our chosen AWS region
    client = TranscribeStreamingClient(region=args.region)

    # Start transcription to generate our async stream
    stream = await client.start_stream_transcription(
        language_code=args.source,
        media_sample_rate_hz=args.samplerate,
        media_encoding="pcm",
    )

    # Instantiate our handler and start processing events
    handler = MyEventHandler(stream.output_stream)
    handler.queue = queue
    await asyncio.gather(write_chunks(stream, args.samplerate), handler.handle_events())

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
            print(result.get('TranslatedText'))

async def main(args):
    queue = asyncio.Queue()
    await asyncio.wait([
        asyncio.create_task(basic_translate(queue, args)),
        asyncio.create_task(basic_transcribe(queue, args))
    ])

parser = argparse.ArgumentParser()
parser.description="Realtime Translate from microphone"
parser.add_argument("-s", "--source", help="Specify input language(e.g. en-US, zh-CN, ja-JP)", type=str, default="en-US")
parser.add_argument("-t", "--target", help="Specify output language", type=str, default="zh-CN")
parser.add_argument("-r", "--region", help="Specify endpoint region", type=str, default="ap-northeast-1")
parser.add_argument("-sr", "--samplerate", help="Specify samplerate in HZ", type=int, default=16000)
args = parser.parse_args()

loop = asyncio.get_event_loop()
loop.run_until_complete(main(args))
loop.close()
