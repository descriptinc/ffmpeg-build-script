#!/bin/bash

if [ $# -ne 3 ]; then
	echo "Required arguments: BUCKET PLATFORM ARCH"
  exit 1
fi

BUCKET=$1
PLATFORM=$2
ARCH=$3

# rename the ffmpeg/ffprobe files
cp build/ffmpeg "build/ffmpeg-$PLATFORM-$ARCH"
cp build/ffprobe "build/ffprobe-$PLATFORM-$ARCH"

# upload to s3
s3cmd put "build/ffmpeg-$PLATFORM-$ARCH" "build/ffprobe-$PLATFORM-$ARCH" "s3://$BUCKET/"
