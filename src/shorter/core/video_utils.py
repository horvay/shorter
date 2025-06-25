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
) -> bool:
    """
    Removes silent sections from a video using ffmpeg.

    Args:
        input_path: Path to the input video.
        output_path: Path to save the processed video.
        silence_threshold: The noise level to be considered silence.
        silence_duration: The duration of silence to be removed (in seconds).

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

    # Step 3: Generate ffmpeg filter to remove silence
    clips = []
    last_end = 0.0
    for start, end in zip(silence_starts, silence_ends):
        start, end = float(start), float(end)
        clips.append(f"between(t,{last_end},{start})")
        last_end = end

    # Add the last segment of the video
    clips.append(f"gte(t,{last_end})")

    select_filter = "+".join(clips)

    # Step 4: Run ffmpeg command to apply filter
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