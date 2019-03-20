# this builtin is needed so we can overwrite in test
import json
import logging

import aiohttp
from async_generator import async_generator, yield_
from prompt_toolkit.styles import Style

import questionary
import rasa.cli.utils
from rasa.cli import utils as cliutils
from rasa_core import utils
from rasa_core.channels import UserMessage
from rasa_core.channels.channel import (
    RestInput, button_to_string, element_to_string)
from rasa_core.constants import DEFAULT_SERVER_URL
from rasa_core.interpreter import INTENT_MESSAGE_PREFIX

logger = logging.getLogger(__name__)


def print_bot_output(message, color=rasa.cli.utils.bcolors.OKBLUE):
    if "text" in message:
        rasa.cli.utils.print_color(message.get("text"),
                                   color)

    if "image" in message:
        rasa.cli.utils.print_color("Image: " + message.get("image"),
                                   color)

    if "attachment" in message:
        rasa.cli.utils.print_color("Attachment: " + message.get("attachment"),
                                   color)

    if "buttons" in message:
        rasa.cli.utils.print_color("Buttons:", color)
        for idx, button in enumerate(message.get("buttons")):
            rasa.cli.utils.print_color(button_to_string(button, idx), color)

    if "elements" in message:
        for idx, element in enumerate(message.get("elements")):
            element_str = "Elements:\n" + element_to_string(element, idx)
            rasa.cli.utils.print_color(element_str, color)

    if "quick_replies" in message:
        for idx, element in enumerate(message.get("quick_replies")):
            element_str = "Quick Replies:\n" + button_to_string(element, idx)
            rasa.cli.utils.print_color(element_str, color)


def get_cmd_input():
    response = questionary.text("",
                                qmark="Your input ->",
                                style=Style([('qmark', '#b373d6'),
                                             ('', '#b373d6')])).ask()
    if response is not None:
        return response.strip()
    else:
        return None


async def send_message_receive_block(server_url,
                                     auth_token,
                                     sender_id,
                                     message):
    payload = {
        "sender": sender_id,
        "message": message
    }

    url = "{}/webhooks/rest/webhook?token={}".format(server_url, auth_token)
    async with aiohttp.ClientSession() as session:
        async with session.post(url,
                                json=payload,
                                raise_for_status=True) as resp:
            return await resp.json()


@async_generator  # needed for python 3.5 compatibility
async def send_message_receive_stream(server_url,
                                      auth_token,
                                      sender_id,
                                      message):
    payload = {
        "sender": sender_id,
        "message": message
    }

    url = "{}/webhooks/rest/webhook?stream=true&token={}".format(
        server_url, auth_token)

    # TODO: check if this properly receives UTF-8 data
    async with aiohttp.ClientSession() as session:
        async with session.post(url,
                                json=payload,
                                raise_for_status=True) as resp:

            async for line in resp.content:
                if line:
                    await yield_(json.loads(line.decode("utf-8")))


async def record_messages(server_url=DEFAULT_SERVER_URL,
                          auth_token=None,
                          sender_id=UserMessage.DEFAULT_SENDER_ID,
                          max_message_limit=None,
                          use_response_stream=True):
    """Read messages from the command line and print bot responses."""

    auth_token = auth_token if auth_token else ""

    exit_text = INTENT_MESSAGE_PREFIX + 'stop'

    cliutils.print_success("Bot loaded. Type a message and press enter "
                           "(use '{}' to exit): ".format(exit_text))

    num_messages = 0
    while not utils.is_limit_reached(num_messages, max_message_limit):
        text = get_cmd_input()
        if text == exit_text or text is None:
            break

        if use_response_stream:
            bot_responses = send_message_receive_stream(server_url,
                                                        auth_token,
                                                        sender_id, text)
            async for response in bot_responses:
                print_bot_output(response)
        else:
            bot_responses = await send_message_receive_block(server_url,
                                                             auth_token,
                                                             sender_id, text)
            for response in bot_responses:
                print_bot_output(response)

        num_messages += 1
    return num_messages


class CmdlineInput(RestInput):

    @classmethod
    def name(cls):
        return "cmdline"

    def url_prefix(self):
        return RestInput.name()
