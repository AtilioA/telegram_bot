#!/usr/bin/env python

import logging
import os
import random
import argparse
from enum import Enum

import requests
from langcodes import standardize_tag
from urllib.parse import quote
from telegram.ext.dispatcher import run_async
from google.cloud import texttospeech

speakLogger = logging.getLogger(__name__)
speakLogger.setLevel(logging.DEBUG)


parser = argparse.ArgumentParser()
parser.add_argument("-w", action="store_true", default=None)
parser.add_argument("-m", action="store_true", default=None)
parser.add_argument("-l", default="pt-BR")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "api_key.json"
GCP_TTS_CHAR_LIMIT = 22


# Instantiate Google TTS client
client = texttospeech.TextToSpeechClient()

# Select the type of audio file
audio_config = texttospeech.AudioConfig(
    audio_encoding=texttospeech.AudioEncoding.LINEAR16
)


class SsmlVoiceGender(Enum):
    SSML_VOICE_GENDER_UNSPECIFIED = 0
    MALE = 1
    FEMALE = 2
    NEUTRAL = 3


def help():
    return (
        "/speak - Manda uma mensagem de voz com o texto.\n*Uso*: /speak texto\n"
        + 'Para falar em inglês, escreva também o parâmetro "-l". Uso: /speak -l en-US text in english.\n'
        + "Isto vale para quase qualquer idioma, utilizando o padrão [BCP-47](https://en.wikipedia.org/wiki/IETF_language_tag).\n"
        + "\nO gênero da voz é aleatório por padrão:\n"
        + 'Para usar uma voz masculina, utilize o parâmetro "-m". Uso: /speak -m texto.\n'
        + 'Para usar uma voz feminina, utilize o parâmetro "-w".\n'
        + "\nOs parâmetros podem ser colocados em qualquer lugar da mensagem."
    )


def wavenet_speak(update, context, sentence, language, gender=None):
    # Set the text input to be synthesized
    synthesis_input = texttospeech.SynthesisInput(text=sentence)

    # if not gender:
    #     gender = "SSML_VOICE_GENDER_UNSPECIFIED"
    if gender and "w" in gender:
        gender = "FEMALE"
    else:
        gender = "MALE"

    # Get available voices
    voices = client.list_voices()
    BCP47lang = standardize_tag(language)

    selectedVoices = [
        voice.name
        for voice in voices.voices
        if (
            str(voice.ssml_gender) == str(SsmlVoiceGender[gender])
            and BCP47lang in voice.language_codes
            and "Standard" not in voice.name
        )
    ]

    try:
        selectedVoice = random.choice(selectedVoices)
    except Exception as e:
        speakLogger.debug("Falha ao criar mensagem de voz com WaveNet."),
        speakLogger.warning(e)
        speakLogger.debug("Defaulting to standard TTS...")
        return original_speak(update, context)


    # Build the voice request, select the language code and the ssml
    voice = texttospeech.VoiceSelectionParams(
        name=selectedVoice,
        language_code=selectedVoice[:5],  # BCP-47 tag
        # ssml_gender=getattr(texttospeech.SsmlVoiceGender, gender)  # Apparently redundant
    )

    # Perform the text-to-speech request on the text input with the selected
    # voice parameters and audio file type
    response = client.synthesize_speech(
        request={"input": synthesis_input, "voice": voice, "audio_config": audio_config}
    )

    return response


@run_async
def original_speak(update, context):
    # Default is pt-br
    engine = "3"
    lang = "6"  # Portuguese
    voice = "2"  # Rafael

    args = context.args
    if not args and update.message.reply_to_message:
        args = update.message.reply_to_message.text.split(" ")

    if "-en" in args:
        engine = "4"
        voice = "5"  # Daniel
        lang = "1"  # English
        args.pop(args.index("-en"))

    if "-pt" in args:
        args.pop(args.index("-pt"))

    if "-w" in args:
        if "-en" in args:
            engine = "3"
            voice = "6"  # Ashley
        else:
            engine = "3"
            voice = "1"  # Helena
        args.pop(args.index("-w"))

    text_to_speech = " ".join(args)

    if not text_to_speech:
        update.message.reply_text(
            'Nada a se falar, coloque a frase a ser falada após o comando, ex.: "/speak cachorro quente"'
        )
        return

    # Make speech url
    text_to_speech = quote(text_to_speech)
    url = f'{BASE_URL}/{engine}/{lang}/{voice}/{text_to_speech}'
    try:
        r = requests.get(url, stream=True)
        if r.status_code != 200:
            raise requests.exceptions.RequestException
    except requests.exceptions.RequestException:
        update.message.reply_text(text="Falha ao criar mensagem de voz.",
                                  reply_to_message_id=update.message.message_id)
        return

    try:
        update.message.reply_voice(voice=r.raw)
    except Exception:
        update.message.reply_text(text="Falha ao criar mensagem de voz.")


@run_async
def speak(update, context):
    if hasattr(update.message, "text") and "-help" in update.message.text:
        update.message.reply_text(
            help(),
            parse_mode="markdown",
            disable_web_page_preview=True,
        )
        return

    lang = "pt-BR"
    gender = None

    args = context.args

    args, unknownArgs = parser.parse_known_args(args)
    textToSpeech = " ".join(unknownArgs)

    lang = args.l
    if args.w:
        gender = "w"
    elif args.m:
        gender = "m"

    replyID = update.message.message_id
    if update.message.reply_to_message:
        textToSpeech = update.message.reply_to_message.text
        replyID = update.message.reply_to_message.message_id

    if not textToSpeech:
        update.message.reply_text(
            'Nada a se falar, coloque a frase a ser falada após o comando, ex.: "/speak cachorro quente"'
        )
        return

    try:
        if len(textToSpeech.strip()) <= GCP_TTS_CHAR_LIMIT:
            wavenetResponse = wavenet_speak(update, context, textToSpeech.strip()[:GCP_TTS_CHAR_LIMIT], lang, gender)
        else:
            raise ValueError(f"String is longer than {GCP_TTS_CHAR_LIMIT}.")

        try:
            update.message.reply_voice(
                voice=wavenetResponse.audio_content, reply_to_message_id=replyID
            )
        except Exception as e:
            speakLogger.debug("Falha ao criar mensagem de voz com WaveNet."),
            speakLogger.warning(e)
            return original_speak(update, context)

    except Exception as e:
        speakLogger.debug("Falha ao criar mensagem de voz com WaveNet."),
        speakLogger.warning(e)
        return original_speak(update, context)
