
A tool running on MAC and translating in real time through microphone

reference resources: https://github.com/awslabs/amazon-transcribe-streaming-sdk/blob/develop/examples/simple_mic.py

# Setup

```bash
pip3 install -r requirements.txt
```

# Usage

## default is English -> Chinese

```bash
python3 realtimetrans.py
```

## sometimes ... maybe it is useful for Japanese -> Chinese

```bash
python3 realtimetrans.py -s ja-JP
```

## -h for help

```bash
python3 realtimetrans.py -h
```
