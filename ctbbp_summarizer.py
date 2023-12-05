from pytube import YouTube
import datetime
import textwrap
import os
from pydub import AudioSegment
from openai import OpenAI
from pydub.utils import mediainfo
from dotenv import load_dotenv
import sys

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)


def summarize_text(prompt):
    print("Summarizing episode...")
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


def get_yt_video(url: str, filename: str):
    yt = YouTube(url)
    _ = yt.streams.first()  # for some reason this needs to be done to get description. See https://github.com/pytube/pytube/issues/1626
    video_title = yt.title
    video_length = datetime.timedelta(seconds=yt.length)
    video_desc = '\n'.join(line for line in yt.description.split('\n') if line.strip())

    audio_stream = yt.streams.filter(only_audio=True).first()
    # Download the audio
    audio_stream.download(output_path=".", filename=filename)

    return video_title, video_length, video_desc


def split_audio(filename: str):
    audio = AudioSegment.from_file(filename)

    # Get bitrate. Using default causes each split file to be bigger than the original
    info = mediainfo(filename)
    bitrate = info['bit_rate']

    # Calculate the split point (half the length of the audio)
    split_point = len(audio) // 2

    # Split the audio into two halves
    first_half = audio[:split_point]
    second_half = audio[split_point:]

    # Export the halves as new audio files
    first_half.export('first_half.mp3', format='mp3', bitrate=bitrate)
    second_half.export('second_half.mp3', format='mp3', bitrate=bitrate)


def transcribe_audio_file(file_name):
    with open(file_name, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1", file=audio_file
        )
    return transcript.text


def write_speech_to_text(audio_files: list):
    print("Transcribing Audio...")
    for audio_file in audio_files:
        transcription_text = transcribe_audio_file(audio_file)
        with open("episode_text.txt", "a") as w_file:
            w_file.write(textwrap.fill(transcription_text, width=80))
            w_file.write("\n")


def generate_prompt(video_title: str, video_length, video_desc: str, episode_text: str, url: str):
    prompt = f"""
    I am providing text I transcribed from an episode of the critical thinking podcast. 
    The podcast covers various aspects of bug bounty programs, including experiences of bug bounty hunters, strategies 
    for finding vulnerabilities, and the impact on cybersecurity. I'd like you to generate markdown using the below template 
    based on the podcast:


    ### {video_title}

    Watch on Youtube

    #### Duration

    #### Summary

    #### Key Takeaways

    #### Techniques and Tools

    #### Notable Mentions

    #### Video Description


    Here is the information:
    Please stick to the template and do not add extra sections.

    Watch on Youtube: make this into a hyperlink using this url: {url} 

    Duration: use this duration {video_length} 

    Summary: Give a concise overview of the podcast, including the main topics discussed and any key points or arguments made about bug bounties.

    Key takeaways: List the most important insights or lessons from the podcast related to bug bounty hunting, such as effective strategies, common challenges, and tips for success in this field.

    Techniques and Tools: List and Describe any and all specific methods, techniques, or tools mentioned in the podcast that are used in bug bounty hunting. Include information on how these techniques contribute to finding and reporting vulnerabilities.

    Notable mentions: Highlight any and all significant guests, stories, or examples mentioned in the podcast that provide valuable insights into the world of bug bounties. Explain why these are important and how they contribute to understanding bug bounty programs.

    Video Description: {video_desc}

    Please ensure the summary is accurate and captures the essence of the podcast discussion.
    Here is the text you should use for the Brief Summary, Key takeways, Techniques and Tools, and notable mentions. 
    Don't Change the text under Video Description. 

    Episode Text: 
    {episode_text}
    """

    return prompt


def clean_up(files):
    for file in files:
        if os.path.exists(file):
            os.remove(file)


def main():
    if len(sys.argv) != 3:
        print("Usage: python ctbbp_summarizer.py <URL> <Output Path>")
        sys.exit(1)

    url = sys.argv[1]
    output_path = sys.argv[2]
    audio_filename = "ctbbp_audio.mp3"

    # Download audio stream and get video details from YouTube
    print("Downloading Youtube video and extracting information...")
    video_title, video_length, video_desc = get_yt_video(url, audio_filename)

    file_size_bytes = os.path.getsize(audio_filename)
    file_size_mb = file_size_bytes / (1024 * 1024)

    print(f"Download completed! The size of the audio file is: {file_size_mb:.2f} MB.")
    if file_size_mb > 25:
        print("Audio file too large. Need to split..")
        split_audio(audio_filename)
        write_speech_to_text(["first_half.mp3", "second_half.mp3"])
    else:
        write_speech_to_text([audio_filename])

    with open("episode_text.txt", "r") as file:
        episode_text = file.read()

    prompt = generate_prompt(video_title, video_length, video_desc, episode_text, url)
    summary_text = summarize_text(prompt)
    print("Summarizing done. Writing to file")
    with open(f"{output_path}.md", "w") as wfile:
        wfile.write(summary_text)

    print("Cleaning up..")
    clean_up([audio_filename, "episode_text.txt", "first_half.mp3", "second_half.mp3"])

    print("All Done! Enjoy!")

if __name__ == "__main__":
    main()
