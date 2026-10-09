"""Interface Discord (fine couche autour de CommandHandler)."""
from __future__ import annotations

import asyncio
import logging

import discord

from . import config
from .commands import CommandHandler

log = logging.getLogger("versus")


def make_client(handler: CommandHandler, message_content: bool) -> discord.Client:
    intents = discord.Intents.default()
    intents.message_content = message_content
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        log.info("Connecté en tant que %s", client.user)

    @client.event
    async def on_message(msg: discord.Message):
        if msg.author.bot:
            return
        text = (msg.content or "").strip()
        is_dm = msg.guild is None
        if not is_dm and not text.startswith(config.PREFIX):
            return
        attachment = None
        if msg.attachments and msg.attachments[0].filename.lower().endswith(".json") \
                and msg.attachments[0].size < 2_000_000:
            attachment = (msg.attachments[0].filename, await msg.attachments[0].read())
        if not text and not attachment:
            return
        async with msg.channel.typing():
            try:
                replies = await asyncio.to_thread(handler.handle, text, msg.author.id, attachment)
            except Exception:
                log.exception("Erreur de traitement")
                replies = ["Erreur interne : la question n'a pas pu être traitée."]
        for r in replies:
            await msg.channel.send(r)

    return client


def run(handler: CommandHandler, token: str):
    try:
        make_client(handler, True).run(token, log_handler=None)
    except discord.PrivilegedIntentsRequired:
        log.warning("Intent 'Message Content' non activé : seuls les MP fonctionneront. "
                    "Active-le dans le portail développeur pour les commandes sur serveur.")
        make_client(handler, False).run(token, log_handler=None)
