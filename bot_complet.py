import io
import os
import urllib.parse
import asyncio
import time
import aiohttp
import discord

from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from google import genai

import threading
from flask import Flask


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Dernier modèle Gemini utilisé
GEMINI_MODEL = "gemini-3.5-flash"

if not GEMINI_API_KEY:
    raise ValueError(
        "❌ GEMINI_API_KEY est introuvable."
    )

if not DISCORD_TOKEN:
    raise ValueError(
        "❌ DISCORD_TOKEN est introuvable."
    )


# ============================================================
# CLIENT GEMINI
# ============================================================

client_ai = genai.Client(
    api_key=GEMINI_API_KEY
)


# ============================================================
# DISCORD
# ============================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# SERVEUR FLASK POUR RENDER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "KayouBot est en ligne !"


def lancer_serveur_web():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    print(
        f"🌐 Serveur Flask démarré sur le port {port}"
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


threading.Thread(
    target=lancer_serveur_web,
    daemon=True
).start()


# ============================================================
# HISTORIQUE
# ============================================================

conversation_history: dict[int, list] = {}

SYSTEM_PROMPT = (
    "Tu es KayouBot, un assistant IA sympa et serviable "
    "sur un serveur Discord. "
    "Tu réponds toujours en français sauf si l'utilisateur "
    "demande une autre langue. "
    "Tu réponds de façon claire, naturelle et concise. "
    "Tu peux utiliser des emojis avec modération. "
    "Si une réponse est longue, utilise du Markdown "
    "compatible avec Discord."
)


# ============================================================
# GEMINI
# ============================================================

async def demander_gemini(prompt: str) -> str:

    def appel_gemini():

        dernier_erreur = None

        for tentative in range(3):

            try:

                print(
                    f"🤖 Requête Gemini "
                    f"(tentative {tentative + 1}/3)"
                )

                response = client_ai.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                )

                return response.text or ""

            except Exception as e:

                dernier_erreur = e

                erreur = str(e)

                print(
                    f"❌ Erreur Gemini : {erreur}"
                )

                if (
                    "503" in erreur
                    or "UNAVAILABLE" in erreur
                    or "429" in erreur
                    or "RESOURCE_EXHAUSTED" in erreur
                ):

                    if tentative < 2:

                        print(
                            "⏳ Gemini est temporairement "
                            "indisponible."
                        )

                        time.sleep(3)

                    continue

                raise

        raise dernier_erreur

    return await asyncio.to_thread(
        appel_gemini
    )


# ============================================================
# HISTORIQUE + IA
# ============================================================

async def appeler_ia(user_id: int, question: str) -> str:
    """
    Appelle Gemini avec l'historique de conversation de l'utilisateur.
    """

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # Ajouter la question
    conversation_history[user_id].append(
        {
            "role": "user",
            "content": question
        }
    )

    # Garder les 20 derniers messages
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = (
            conversation_history[user_id][-20:]
        )

    # Construire le contexte pour Gemini
    lignes = [SYSTEM_PROMPT, "", "Historique de conversation :"]

    for message in conversation_history[user_id]:
        if message["role"] == "user":
            lignes.append(
                f"Utilisateur : {message['content']}"
            )
        else:
            lignes.append(
                f"KayouBot : {message['content']}"
            )

    lignes.append("")
    lignes.append(
        "Réponds au dernier message de l'utilisateur."
    )

    prompt = "\n".join(lignes)

    answer = await demander_gemini(prompt)

    # Ajouter la réponse à l'historique
    conversation_history[user_id].append(
        {
            "role": "assistant",
            "content": answer
        }
    )

    return answer


# ============================================================
# ENVOI DE RÉPONSE DISCORD
# ============================================================

async def envoyer_reponse(
    interaction: discord.Interaction,
    answer: str
):
    """
    Discord limite les messages à 2000 caractères.
    On découpe les réponses trop longues.
    """

    if not answer:
        answer = "❌ Gemini n'a retourné aucune réponse."

    # Limite légèrement inférieure à 2000 pour éviter les problèmes
    limite = 1900

    chunks = [
        answer[i:i + limite]
        for i in range(0, len(answer), limite)
    ]

    await interaction.followup.send(chunks[0])

    for chunk in chunks[1:]:
        await interaction.channel.send(chunk)


# ============================================================
# ÉVÉNEMENT BOT PRÊT
# ============================================================

@bot.event
async def on_ready():

    try:
        await bot.tree.sync()

        print(
            f"✅ Bot connecté en tant que {bot.user}"
        )

        print(
            "✅ Commandes slash synchronisées"
        )

        print(
            f"✅ Gemini actif avec le modèle : {GEMINI_MODEL}"
        )

    except Exception as e:

        print(
            f"❌ Erreur lors de la synchronisation : {e}"
        )


# ============================================================
# /IA
# ============================================================

@bot.tree.command(
    name="ia",
    description="Pose une question à KayouBot"
)
@app_commands.describe(
    question="Ta question à l'intelligence artificielle"
)
async def ia(
    interaction: discord.Interaction,
    question: str
):

    await interaction.response.defer()

    try:

        answer = await appeler_ia(
            interaction.user.id,
            question
        )

        await envoyer_reponse(
            interaction,
            answer
        )

    except Exception as e:

        print(
            f"❌ Erreur /ia : {e}"
        )

        await interaction.followup.send(
            f"❌ Une erreur est survenue avec Gemini :\n`{e}`"
        )


# ============================================================
# /RESET
# ============================================================

@bot.tree.command(
    name="reset",
    description="Réinitialise ta conversation avec KayouBot"
)
async def reset(
    interaction: discord.Interaction
):

    user_id = interaction.user.id

    if user_id in conversation_history:
        del conversation_history[user_id]

    await interaction.response.send_message(
        "🔄 Ta conversation a été réinitialisée !",
        ephemeral=True
    )


# ============================================================
# /IMAGINE
# ============================================================

@bot.tree.command(
    name="imagine",
    description="Génère une image à partir d'une description"
)
@app_commands.describe(
    description="Décris l'image que tu veux générer"
)
async def imagine(
    interaction: discord.Interaction,
    description: str
):

    await interaction.response.defer()

    try:

        prompt_encode = urllib.parse.quote(
            description
        )

        url = (
            "https://image.pollinations.ai/prompt/"
            f"{prompt_encode}"
            "?width=1024"
            "&height=1024"
            "&nologo=true"
        )

        timeout = aiohttp.ClientTimeout(
            total=60
        )

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(url) as resp:

                if resp.status == 200:

                    image_data = await resp.read()

                    file = discord.File(
                        fp=io.BytesIO(image_data),
                        filename="kayoubot_image.png"
                    )

                    await interaction.followup.send(
                        content=f"🎨 **{description}**",
                        file=file
                    )

                else:

                    await interaction.followup.send(
                        "❌ Impossible de générer l'image."
                    )

    except Exception as e:

        print(
            f"❌ Erreur /imagine : {e}"
        )

        await interaction.followup.send(
            f"❌ Erreur lors de la génération : `{e}`"
        )


# ============================================================
# /TRADUIS
# ============================================================

@bot.tree.command(
    name="traduis",
    description="Traduit un texte dans la langue choisie"
)
@app_commands.describe(
    texte="Le texte à traduire",
    langue="La langue cible, par exemple anglais, espagnol ou japonais"
)
async def traduis(
    interaction: discord.Interaction,
    texte: str,
    langue: str
):

    await interaction.response.send_message(
        "⏳ Traduction en cours..."
    )

    try:

        prompt = (
            f"Tu es un traducteur professionnel.\n"
            f"Traduis le texte suivant en {langue}.\n"
            f"Réponds uniquement avec la traduction, "
            f"sans explication supplémentaire.\n\n"
            f"Texte :\n{texte}"
        )

        answer = await demander_gemini(
            prompt
        )

        await interaction.edit_original_response(
            content=(
                f"🌍 **Traduction en {langue} :**\n"
                f"{answer}"
            )
        )

    except Exception as e:

        print(
            f"❌ Erreur /traduis : {e}"
        )

        await interaction.edit_original_response(
            content=f"❌ Erreur : {e}"
        )


# ============================================================
# /RESUME
# ============================================================

@bot.tree.command(
    name="resume",
    description="Résume un texte long"
)
@app_commands.describe(
    texte="Le texte à résumer"
)
async def resume(
    interaction: discord.Interaction,
    texte: str
):

    await interaction.response.send_message(
        "⏳ Résumé en cours..."
    )

    try:

        prompt = (
            "Tu es un assistant spécialisé dans le résumé de textes.\n"
            "Fais un résumé clair, fidèle et concis du texte suivant.\n\n"
            f"Texte :\n{texte}"
        )

        answer = await demander_gemini(
            prompt
        )

        await interaction.edit_original_response(
            content=(
                f"📝 **Résumé :**\n"
                f"{answer}"
            )
        )

    except Exception as e:

        print(
            f"❌ Erreur /resume : {e}"
        )

        await interaction.edit_original_response(
            content=f"❌ Erreur : {e}"
        )


# ============================================================
# /BLAGUE
# ============================================================

@bot.tree.command(
    name="blague",
    description="Raconte une blague aléatoire"
)
async def blague(
    interaction: discord.Interaction
):

    await interaction.response.send_message(
        "⏳ Je cherche une blague..."
    )

    try:

        prompt = (
            "Tu es un comédien français.\n"
            "Raconte une blague courte et drôle en français.\n"
            "Réponds uniquement avec la blague."
        )

        answer = await demander_gemini(
            prompt
        )

        await interaction.edit_original_response(
            content=f"😂 {answer}"
        )

    except Exception as e:

        print(
            f"❌ Erreur /blague : {e}"
        )

        await interaction.edit_original_response(
            content=f"❌ Erreur : {e}"
        )


# ============================================================
# /HELP
# ============================================================

@bot.tree.command(
    name="help",
    description="Affiche la liste des commandes"
)
async def help_command(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="🤖 KayouBot — Aide",
        description=(
            "Voici toutes les commandes disponibles :"
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="/ia [question]",
        value=(
            "Pose une question à KayouBot. "
            "Il conserve l'historique de ta conversation."
        ),
        inline=False
    )

    embed.add_field(
        name="/reset",
        value=(
            "Efface ton historique de conversation."
        ),
        inline=False
    )

    embed.add_field(
        name="/imagine [description]",
        value=(
            "Génère une image à partir d'une description."
        ),
        inline=False
    )

    embed.add_field(
        name="/traduis",
        value=(
            "Traduit un texte dans la langue choisie."
        ),
        inline=False
    )

    embed.add_field(
        name="/resume",
        value=(
            "Résume un texte long."
        ),
        inline=False
    )

    embed.add_field(
        name="/blague",
        value=(
            "Raconte une blague aléatoire."
        ),
        inline=False
    )

    embed.add_field(
        name="/help",
        value=(
            "Affiche ce message d'aide."
        ),
        inline=False
    )

    embed.set_footer(
        text="Propulsé par Google Gemini 🤖"
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# MODÉRATION AUTOMATIQUE
# ============================================================

@bot.event
async def on_message(
    message: discord.Message
):

    # Ignorer les messages du bot
    if message.author == bot.user:
        return

    # Ne pas modérer les messages vides
    if not message.content.strip():
        await bot.process_commands(message)
        return

    # Les commandes préfixées ne sont pas modérées ici
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    try:

        prompt = (
            "Tu es un modérateur automatique de serveur Discord.\n"
            "Analyse le message suivant.\n\n"
            "Réponds UNIQUEMENT par INAPPROPRIE si le message contient "
            "des insultes graves, du harcèlement ciblé, du contenu "
            "sexuel explicite ou de la haine visant un groupe protégé.\n"
            "Sinon réponds UNIQUEMENT par OK.\n\n"
            f"Message : {message.content}"
        )

        verdict = await demander_gemini(
            prompt
        )

        verdict = verdict.strip().upper()

        if "INAPPROPRIE" in verdict:

            try:

                await message.delete()

                avertissement = await message.channel.send(
                    f"⚠️ {message.author.mention}, "
                    "ton message a été supprimé car il enfreint "
                    "les règles du serveur."
                )

                await asyncio.sleep(5)

                await avertissement.delete()

            except discord.Forbidden:

                print(
                    "❌ Permissions insuffisantes "
                    "pour supprimer le message."
                )

    except Exception as e:

        print(
            f"❌ Erreur modération : {e}"
        )

    # Permettre aux commandes Discord de fonctionner
    await bot.process_commands(message)


# ============================================================
# LANCEMENT DU BOT
# ============================================================

import threading
from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return "KayouBot est en ligne !"


def lancer_serveur_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )


threading.Thread(
    target=lancer_serveur_web,
    daemon=True
).start()

print("🚀 Démarrage de KayouBot...")

bot.run(DISCORD_TOKEN)
