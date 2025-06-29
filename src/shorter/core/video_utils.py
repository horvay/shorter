import subprocess
import os
import re

def cut_video(
    input_path: str,
    output_path: str,
    start_time: str,
    end_time: str,
    is_vertical: bool = False,
) -> bool:
    """
    Cuts a video using ffmpeg.

    Args:
        input_path: Path to the input video.
        output_path: Path to save the cut video.
        start_time: Start time in HH:MM:SS format.
        end_time: End time in HH:MM:SS format.
        is_vertical: If true, creates a vertical short.

    Returns:
        True if successful, False otherwise.
    """
    if not os.path.exists(os.path.dirname(output_path)):
        os.makedirs(os.path.dirname(output_path))

    if is_vertical:
        # Command for vertical short
        # Scales video to fit width and pads to 1080x1920
        # Puts the video 1/3rd from the top of the vertical video
        command = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-ss", start_time,
            "-to", end_time,
            "-vf", "crop=iw*0.9:ih,scale=1080:-1,pad=1080:1920:(ow-iw)/2:(oh-ih)/3:color=black",
            "-c:a", "copy",
            output_path,
        ]
    else:
        # Command for normal cut
        command = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-ss", start_time,
            "-to", end_time,
            "-c", "copy",
            output_path,
        ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error cutting video: {e.stderr}")
        return False

def remove_silence(
    input_path: str,
    output_path: str,
    silence_threshold: str = "-30dB",
    silence_duration: float = 1.0,
    padding: float = 0.5,
) -> bool:
    """
    Removes silent sections from a video using ffmpeg, leaving padding.

    Args:
        input_path: Path to the input video.
        output_path: Path to save the processed video.
        silence_threshold: The noise level to be considered silence.
        silence_duration: The duration of silence to be detected (in seconds).
        padding: The duration of silence to leave at the start and end of a cut.

    Returns:
        True if successful, False otherwise.
    """
    if not os.path.exists(os.path.dirname(output_path)):
        os.makedirs(os.path.dirname(output_path))

    # Step 1: Detect silence
    detect_command = [
        "ffmpeg", "-i", input_path, "-af",
        f"silencedetect=n={silence_threshold}:d={silence_duration}",
        "-f", "null", "-",
    ]

    try:
        output = subprocess.run(
            detect_command,
            check=True,
            capture_output=True,
            text=True,
        ).stderr
    except subprocess.CalledProcessError as e:
        print(f"Error detecting silence: {e.stderr}")
        return False

    # Step 2: Parse silence timestamps
    silence_starts = re.findall(r"silence_start: (\d+\.?\d*)", output)
    silence_ends = re.findall(r"silence_end: (\d+\.?\d*)", output)

    if not silence_starts:
        print("No silence detected, copying file.")
        if input_path != output_path:
             subprocess.run(["cp", input_path, output_path], check=True)
        return True

    # Step 3: Create list of chunks to remove, including padding
    chunks_to_remove = []
    for start, end in zip(silence_starts, silence_ends):
        start, end = float(start), float(end)
        # Only cut if the silence is long enough for the padding
        if end - start > 2 * padding:
            chunks_to_remove.append((start + padding, end - padding))

    if not chunks_to_remove:
        print("No silences long enough to cut after padding, copying file.")
        if input_path != output_path:
            subprocess.run(["cp", input_path, output_path], check=True)
        return True

    # Step 4: Generate ffmpeg filter to remove chunks
    clips = []
    last_end = 0.0
    for start, end in sorted(chunks_to_remove):
        clips.append(f"between(t,{last_end},{start})")
        last_end = end

    # Add the last segment of the video
    clips.append(f"gte(t,{last_end})")

    select_filter = "+".join(clips)

    # Step 5: Run ffmpeg command to apply filter
    process_command = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"select='{select_filter}',setpts=N/FRAME_RATE/TB",
        "-af", f"aselect='{select_filter}',asetpts=N/SR/TB",
        output_path,
    ]

    try:
        subprocess.run(process_command, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error removing silence: {e.stderr}")
        return False

def remove_chunks(
    input_path: str,
    output_path: str,
    chunks_to_remove: list[tuple[float, float]],
) -> bool:
    """
    Removes specified chunks from a video using ffmpeg.

    Args:
        input_path: Path to the input video.
        output_path: Path to save the processed video.
        chunks_to_remove: A list of (start, end) tuples for chunks to remove.

    Returns:
        True if successful, False otherwise.
    """
    if not os.path.exists(os.path.dirname(output_path)):
        os.makedirs(os.path.dirname(output_path))

    if not chunks_to_remove:
        print("No chunks to remove, copying file.")
        if input_path != output_path:
            subprocess.run(["cp", input_path, output_path], check=True)
        return True

    # Build the ffmpeg filter
    clips = []
    last_end = 0.0
    for start, end in sorted(chunks_to_remove):
        clips.append(f"between(t,{last_end},{start})")
        last_end = end

    clips.append(f"gte(t,{last_end})")

    select_filter = "+".join(clips)

    # Run ffmpeg command
    command = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"select='{select_filter}',setpts=N/FRAME_RATE/TB",
        "-af", f"aselect='{select_filter}',asetpts=N/SR/TB",
        output_path,
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error removing chunks: {e.stderr}")
        return False

def get_video_duration(input_path: str) -> float:
    command = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", input_path
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return float(result.stdout)
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error getting video duration: {e}")
        return 0.0

def get_video_resolution(input_path: str) -> tuple[int, int] | None:
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0", input_path
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        width, height = map(int, result.stdout.strip().split('x'))
        return width, height
    except Exception as e:
        print(f"Error getting video resolution: {e}")
        return None

def speed_up_video(
    input_path: str,
    output_path: str,
    speed: float,
) -> bool:
    """
    Speeds up a video and its audio.

    Args:
        input_path: Path to the input video.
        output_path: Path to save the processed video.
        speed: The speed multiplier (e.g., 2.0 for double speed).

    Returns:
        True if successful, False otherwise.
    """
    if not os.path.exists(os.path.dirname(output_path)):
        os.makedirs(os.path.dirname(output_path))

    # FFmpeg atempo filter maxes out at 2.0, so we chain them for higher speeds
    atempo_filter = ""
    temp_speed = speed
    while temp_speed > 2.0:
        atempo_filter += "atempo=2.0,"
        temp_speed /= 2.0
    atempo_filter += f"atempo={temp_speed}"


    command = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex",
        f"[0:v]setpts=PTS/{speed}[v];[0:a]{atempo_filter}[a]",
        "-map", "[v]",
        "-map", "[a]",
        output_path
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error speeding up video: {e.stderr}")
        return False

def process_zoom_pan(
    input_path: str,
    output_path: str,
    zoom_regions: list[dict],
) -> bool:
    if not zoom_regions:
        print("No zoom regions specified, copying file.")
        if input_path != output_path:
            subprocess.run(["cp", input_path, output_path], check=True)
        return True

    video_duration = get_video_duration(input_path)
    if video_duration == 0.0:
        return False

    # Sort regions by time
    regions = sorted(zoom_regions, key=lambda x: x['time'])

    filter_complex = []
    clip_streams = []
    num_clips = 0

    # Initial un-zoomed segment
    if not regions or regions[0]['time'] > 0:
        end_of_initial = regions[0]['time'] if regions else video_duration
        trim_filter = (
            f"[0:v]trim=start=0:end={end_of_initial},"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/3,"
            f"setsar=1,setpts=PTS-STARTPTS[v{num_clips}];"
        )
        atrim_filter = f"[0:a]atrim=start=0:end={end_of_initial},asetpts=PTS-STARTPTS[a{num_clips}];"
        filter_complex.extend([trim_filter, atrim_filter])
        clip_streams.append(f"[v{num_clips}]")
        clip_streams.append(f"[a{num_clips}]")
        num_clips += 1

    # Process each zoom region
    for i, region in enumerate(regions):
        start_time = region['time']
        end_time = regions[i+1]['time'] if i + 1 < len(regions) else video_duration
        rect = region['rect']

        if end_time <= start_time:
            continue

        crop_filter = (
            f"[0:v]trim=start={start_time}:end={end_time},"
            f"crop={rect.width()}:{rect.height()}:{rect.x()}:{rect.y()},"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/3,"
            f"setsar=1,setpts=PTS-STARTPTS[v{num_clips}];"
        )
        audio_trim_filter = (
             f"[0:a]atrim=start={start_time}:end={end_time},"
             f"asetpts=PTS-STARTPTS[a{num_clips}];"
        )
        filter_complex.extend([crop_filter, audio_trim_filter])
        clip_streams.append(f"[v{num_clips}]")
        clip_streams.append(f"[a{num_clips}]")
        num_clips += 1

    # Concatenate all clips
    concat_streams = "".join(clip_streams)
    concat_filter = f"{concat_streams}concat=n={num_clips}:v=1:a=1[outv][outa]"
    filter_complex.append(concat_filter)

    command = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex", "".join(filter_complex),
        "-map", "[outv]", "-map", "[outa]",
        output_path
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error processing zoom/pan: {e.stderr}")
        return False