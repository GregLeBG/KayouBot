import discord
from discord.ext import commands
from discord import app_commands
from openai import AsyncOpenAI
from dotenv import load_dotenv
import aiohttp
import os

load_dotenv()

client_ai = AsyncOpenAI(
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Historique des conversations par utilisateur
conversation_history: dict[int, list] = {}

# Personnalité du bot
SYSTEM_PROMPT = (
    "Tu es KayouBot, un assistant IA sympa et serviable sur un serveur Discord. "
    "Tu réponds de façon claire et concise. "
    "Tu peux utiliser des emojis avec modération. "
    "Si une réponse est longue, utilise du markdown Discord (** pour gras, ` pour code, etc.)."
)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot connecté en tant que {bot.user}")
    print(f"✅ Commandes slash synchronisées")


async def envoyer_reponse(interaction, answer):
    """Envoie la réponse en découpant si nécessaire."""
    if len(answer) > 1900:
        chunks = [answer[i:i+1900] for i in range(0, len(answer), 1900)]
        await interaction.followup.send(chunks[0])
        for chunk in chunks[1:]:
            await interaction.channel.send(chunk)
    else:
        await interaction.followup.send(answer)


async def appeler_ia(user_id: int, question: str) -> str:
    """Appelle l'IA avec l'historique de conversation."""
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": question})

    # Garder les 20 derniers messages
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    reponse = await client_ai.chat.completions.create(
        model="openrouter/auto",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history[user_id]
    )

    answer = reponse.choices[0].message.content

    conversation_history[user_id].append({"role": "assistant", "content": answer})

    return answer


@bot.tree.command(name="ia", description="Pose une question à l'IA")
async def ia(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    try:
        answer = await appeler_ia(interaction.user.id, question)
        await envoyer_reponse(interaction, answer)
    except Exception as e:
        print(e)
        await interaction.followup.send(f"Erreur : {e}")


@bot.tree.command(name="reset", description="Réinitialise ta conversation avec l'IA")
async def reset(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id in conversation_history:
        del conversation_history[user_id]
    await interaction.response.send_message("🔄 Ta conversation a été réinitialisée !", ephemeral=True)


@bot.tree.command(name="imagine", description="Génère une image à partir d'une description")
async def imagine(interaction: discord.Interaction, description: str):
    await interaction.response.defer()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://image.pollinations.ai/prompt/" + description.replace(" ", "%20"),
            ) as resp:
                if resp.status == 200:
                    image_data = await resp.read()
                    file = discord.File(
                        fp=__import__("io").BytesIO(image_data),
                        filename="image.png"
                    )
                    await interaction.followup.send(f"🎨 **{description}**", file=file)
                else:
                    await interaction.followup.send("❌ Impossible de générer l'image.")
    except Exception as e:
        print(e)
        await interaction.followup.send(f"Erreur : {e}")


@bot.tree.command(name="traduis", description="Traduit un texte dans la langue choisie")
@app_commands.describe(texte="Le texte à traduire", langue="La langue cible (ex: anglais, espagnol, japonais...)")
async def traduis(interaction: discord.Interaction, texte: str, langue: str):
    await interaction.response.send_message("⏳ Traduction en cours...")
    try:
        reponse = await client_ai.chat.completions.create(
            model="openrouter/auto",
            messages=[
                {"role": "system", "content": f"Tu es un traducteur. Traduis le texte suivant en {langue}. Réponds UNIQUEMENT avec la traduction, rien d'autre."},
                {"role": "user", "content": texte}
            ]
        )
        await interaction.edit_original_response(content=f"🌍 **Traduction en {langue} :**\n{reponse.choices[0].message.content}")
    except Exception as e:
        await interaction.edit_original_response(content=f"Erreur : {e}")


@bot.tree.command(name="resume", description="Résume un texte long")
@app_commands.describe(texte="Le texte à résumer")
async def resume(interaction: discord.Interaction, texte: str):
    await interaction.response.send_message("⏳ Résumé en cours...")
    try:
        reponse = await client_ai.chat.completions.create(
            model="openrouter/auto",
            messages=[
                {"role": "system", "content": "Tu es un assistant qui résume des textes. Fais un résumé clair et concis du texte suivant."},
                {"role": "user", "content": texte}
            ]
        )
        await interaction.edit_original_response(content=f"📝 **Résumé :**\n{reponse.choices[0].message.content}")
    except Exception as e:
        await interaction.edit_original_response(content=f"Erreur : {e}")


@bot.tree.command(name="blague", description="Raconte une blague aléatoire")
async def blague(interaction: discord.Interaction):
    await interaction.response.send_message("⏳ Je cherche une blague...")
    try:
        reponse = await client_ai.chat.completions.create(
            model="openrouter/auto",
            messages=[
                {"role": "system", "content": "Tu es un comédien. Raconte une blague courte et drôle en français. Juste la blague, rien d'autre."},
                {"role": "user", "content": "Raconte-moi une blague aléatoire."}
            ]
        )
        await interaction.edit_original_response(content=f"😂 {reponse.choices[0].message.content}")
    except Exception as e:
        await interaction.edit_original_response(content=f"Erreur : {e}")


@bot.tree.command(name="help", description="Affiche la liste des commandes")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 KayouBot — Aide",
        description="Voici toutes les commandes disponibles :",
        color=discord.Color.blurple()
    )
    embed.add_field(
        name="/ia [question]",
        value="Pose une question à l'IA. Elle se souvient de la conversation.",
        inline=False
    )
    embed.add_field(
        name="/reset",
        value="Efface ton historique de conversation pour repartir à zéro.",
        inline=False
    )
    embed.add_field(
        name="/imagine [description]",
        value="Génère une image à partir d'une description.",
        inline=False
    )
    embed.add_field(
        name="/help",
        value="Affiche ce message d'aide.",
        inline=False
    )
    embed.add_field(
        name="/traduis",
        value="Traduit un texte dans la langue choisie.",
        inline=False
    )
    embed.add_field(
        name="/resume",
        value="Résume un texte long.",
        inline=False
    )
    embed.add_field(
        name="/blague",
        value="Raconte une blague aléatoire.",
        inline=False
    )
    embed.set_footer(text="Propulsé par OpenRouter — Gratuit ✅")
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_message(message):
    # Ignorer les messages du bot lui-même
    if message.author == bot.user:
        return

    # Ignorer les commandes
    if message.content.startswith("!"):
        return

    try:
        reponse = await client_ai.chat.completions.create(
            model="openrouter/auto",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un modérateur de serveur Discord. "
                        "Analyse le message suivant et réponds UNIQUEMENT par 'INAPPROPRIE' si le message contient "
                        "des insultes, du harcèlement, du contenu adulte ou de la haine. "
                        "Sinon réponds UNIQUEMENT par 'OK'. Rien d'autre."
                    )
                },
                {"role": "user", "content": message.content}
            ]
        )

        verdict = reponse.choices[0].message.content.strip().upper()

        if "INAPPROPRIE" in verdict:
            await message.delete()
            avertissement = await message.channel.send(
                f"⚠️ {message.author.mention} ton message a été supprimé car il enfreint les règles du serveur."
            )
            # Supprimer l'avertissement après 5 secondes
            await __import__("asyncio").sleep(5)
            await avertissement.delete()

    except Exception as e:
        print(f"Erreur modération : {e}")

    await bot.process_commands(message)


bot.run(os.environ.get("DISCORD_TOKEN"))
