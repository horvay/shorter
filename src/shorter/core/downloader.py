import yt_dlp
import os
from typing import Callable, Optional

def download_video(
    url: str,
    output_path: str,
    progress_hook: Optional[Callable[[dict], None]] = None,
    filename: Optional[str] = None,
) -> bool:
    """
    Downloads a video from a given URL using yt-dlp.

    Args:
        url: The URL of the video to download.
        output_path: The directory to save the video in.
        progress_hook: An optional callback function for progress updates.
        filename: An optional filename for the output file.

    Returns:
        True if download is successful, False otherwise.
    """
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    if filename:
        outtmpl = os.path.join(output_path, f"{filename}.%(ext)s")
    else:
        outtmpl = os.path.join(output_path, "%(title)s.%(ext)s")

    ydl_opts = {
        "format": "best",
        "outtmpl": outtmpl,
        "progress_hooks": [progress_hook] if progress_hook else [],
        "noprogress": True,
        "nopart": True,
        "no_color": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"Error downloading video: {e}")
        return False