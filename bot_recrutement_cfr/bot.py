import os
import sqlite3
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "cfr_bot.sqlite3"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config (
            guild_id INTEGER PRIMARY KEY,
            presentation_channel_id INTEGER NOT NULL,
            recruiter_role_id INTEGER NOT NULL,
            ticket_category_id INTEGER,
            archive_category_id INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (guild_id, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_assignments (
            channel_id INTEGER PRIMARY KEY,
            recruiter_id INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_candidates (
            channel_id INTEGER PRIMARY KEY,
            candidate_id INTEGER NOT NULL
        )
    """)
    try:
        conn.execute("ALTER TABLE config ADD COLUMN archive_category_id INTEGER")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    return conn


def get_config(guild_id: int):
    conn = db()
    row = conn.execute(
        "SELECT presentation_channel_id, recruiter_role_id, ticket_category_id, archive_category_id "
        "FROM config WHERE guild_id = ?",
        (guild_id,)
    ).fetchone()
    conn.close()
    return row


def set_config(
    guild_id: int,
    presentation_id: int,
    recruiter_role_id: int,
    category_id: int | None,
    archive_category_id: int | None
):
    conn = db()
    conn.execute(
        "INSERT INTO config(guild_id, presentation_channel_id, recruiter_role_id, ticket_category_id, archive_category_id) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET "
        "presentation_channel_id=excluded.presentation_channel_id, "
        "recruiter_role_id=excluded.recruiter_role_id, "
        "ticket_category_id=excluded.ticket_category_id, "
        "archive_category_id=excluded.archive_category_id",
        (guild_id, presentation_id, recruiter_role_id, category_id, archive_category_id)
    )
    conn.commit()
    conn.close()


def set_pending(guild_id: int, user_id: int):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO pending(guild_id, user_id) VALUES (?, ?)",
        (guild_id, user_id)
    )
    conn.commit()
    conn.close()


def is_pending(guild_id: int, user_id: int) -> bool:
    conn = db()
    row = conn.execute(
        "SELECT 1 FROM pending WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id)
    ).fetchone()
    conn.close()
    return row is not None


def clear_pending(guild_id: int, user_id: int):
    conn = db()
    conn.execute(
        "DELETE FROM pending WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id)
    )
    conn.commit()
    conn.close()


def get_ticket_assignment(channel_id: int):
    conn = db()
    row = conn.execute(
        "SELECT recruiter_id FROM ticket_assignments WHERE channel_id = ?",
        (channel_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def assign_ticket(channel_id: int, recruiter_id: int):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO ticket_assignments(channel_id, recruiter_id) VALUES (?, ?)",
        (channel_id, recruiter_id)
    )
    conn.commit()
    conn.close()


def unassign_ticket(channel_id: int):
    conn = db()
    conn.execute(
        "DELETE FROM ticket_assignments WHERE channel_id = ?",
        (channel_id,)
    )
    conn.commit()
    conn.close()


def set_ticket_candidate(channel_id: int, candidate_id: int):
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO ticket_candidates(channel_id, candidate_id) VALUES (?, ?)",
        (channel_id, candidate_id)
    )
    conn.commit()
    conn.close()


def get_ticket_candidate(channel_id: int):
    conn = db()
    row = conn.execute(
        "SELECT candidate_id FROM ticket_candidates WHERE channel_id = ?",
        (channel_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def clear_ticket_candidate(channel_id: int):
    conn = db()
    conn.execute(
        "DELETE FROM ticket_candidates WHERE channel_id = ?",
        (channel_id,)
    )
    conn.commit()
    conn.close()


def get_active_ticket_for_candidate(candidate_id: int):
    conn = db()
    row = conn.execute(
        "SELECT channel_id FROM ticket_candidates WHERE candidate_id = ? LIMIT 1",
        (candidate_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


WELCOME_TEXT = """Les **[CFr]** te souhaitent la bienvenue sur leur serveur ! 👋

La team **CFr** est avant tout axée sur la détente et le fun. Nous organisons également quelques événements un peu plus sérieux, comme des **TH, events chars, etc.**, tout en gardant toujours une place importante au plaisir de jouer ensemble.

**Tu souhaites simplement jouer avec nous ?**
Présente-toi en cliquant sur le bouton **« PRÉSENTATION »**. Nous t'accueillerons avec grand plaisir ! 😉

**Tu souhaites nous rejoindre et t'investir davantage dans la team ?**
Tu peux déposer ta candidature en cliquant sur le bouton **« CANDIDATURE »**.

👇 **À toi de jouer !**"""


class PresentationModal(discord.ui.Modal, title="Présentation CFr"):
    texte = discord.ui.TextInput(
        label="Ta présentation",
        placeholder="Remplace la trame ci-dessous par ta présentation.",
        default="[Pseudo ingame]\n\n[Présentation (âge, jeux joué,etc.)]\n\n[Expérience sur le jeu]\n\n[Comment as-tu connu les CFr]",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=4000
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        cfg = get_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message(
                "Le bot n'est pas configuré. Un administrateur doit utiliser `/config`.",
                ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(cfg[0])
        if not channel:
            await interaction.response.send_message(
                "Je ne retrouve pas le salon de présentation.",
                ephemeral=True
            )
            return

        await channel.send(
            content=(
                f"👋 **Présentation de {interaction.user.mention}**\n\n"
                f"{self.texte.value}"
            )
        )
        await interaction.response.send_message(
            f"Ta présentation a bien été envoyée dans {channel.mention} ! 👋",
            ephemeral=True
        )


class CandidatureModal(discord.ui.Modal, title="Candidature CFr"):
    texte = discord.ui.TextInput(
        label="Ta candidature",
        placeholder="Remplace la trame ci-dessous par ta candidature.",
        default="[Pseudo ingame]\n\n[Présentation (âge, jeux joué,etc.)]\n\n[Expérience sur le jeu]\n\n[Comment as-tu connu les CFr]",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=4000
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        cfg = get_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message(
                "Le bot n'est pas configuré. Un administrateur doit utiliser `/config`.",
                ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(cfg[0])
        recruiter_role = interaction.guild.get_role(cfg[1])
        category = interaction.guild.get_channel(cfg[2]) if cfg[2] else None

        if not channel or not recruiter_role:
            await interaction.response.send_message(
                "La configuration du bot est incomplète. Vérifie `/config`.",
                ephemeral=True
            )
            return

        # Publication de la candidature dans #présentation,
        # sous forme de message Discord classique (pas d'embed).
        await channel.send(
            content=(
                f"📋 **Candidature de {interaction.user.mention}**\n\n"
                f"{self.texte.value}"
            )
        )

        # Création du ticket privé Recruteur.
        base_name = "".join(
            c.lower() if c.isalnum() else "-"
            for c in interaction.user.display_name
        ).strip("-") or str(interaction.user.id)
        channel_name = f"recruteur-{base_name}"[:90]

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            ),
            recruiter_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True
            ),
        }

        try:
            ticket = await interaction.guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Candidature de {interaction.user} ({interaction.user.id})",
                reason="Candidature CFr"
            )
            set_ticket_candidate(ticket.id, interaction.user.id)

            ticket_embed = discord.Embed(
                title="📋 Candidature à étudier",
                description=self.texte.value,
                timestamp=discord.utils.utcnow()
            )
            ticket_embed.set_author(
                name=str(interaction.user),
                icon_url=interaction.user.display_avatar.url
            )
            ticket_embed.add_field(
                name="Candidat",
                value=f"{interaction.user.mention}\n`{interaction.user}`",
                inline=False
            )

            # Le ticket est volontairement créé sans boutons.
            await ticket.send(
                content=f"{recruiter_role.mention} — nouvelle candidature de {interaction.user.mention}",
                embed=ticket_embed
            )

            await interaction.response.send_message(
                f"✅ Ta candidature a été envoyée dans {channel.mention} et un ticket privé "
                f"pour les recruteurs a été créé.",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "La candidature a été publiée, mais je n'ai pas les permissions nécessaires "
                "pour créer le ticket. Vérifie les permissions du bot.",
                ephemeral=True
            )


class WelcomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PresentationButton())
        self.add_item(CandidatureButton())


class PresentationButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="PRÉSENTATION",
            emoji="👋",
            style=discord.ButtonStyle.success,
            custom_id="cfr:presentation"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PresentationModal())


class CandidatureButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="CANDIDATURE",
            emoji="📋",
            style=discord.ButtonStyle.primary,
            custom_id="cfr:candidature"
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        existing_ticket_id = get_active_ticket_for_candidate(interaction.user.id)

        if existing_ticket_id:
            existing_ticket = interaction.guild.get_channel(existing_ticket_id)

            if existing_ticket is not None:
                await interaction.response.send_message(
                    f"⚠️ Tu as déjà une candidature en cours dans {existing_ticket.mention}.\n\n"
                    "Tu ne peux pas créer une nouvelle candidature tant que celle-ci n'est pas fermée.",
                    ephemeral=True
                )
                return

            # Le ticket a été supprimé sur Discord mais sa trace existe encore en base.
            clear_ticket_candidate(existing_ticket_id)
            unassign_ticket(existing_ticket_id)

        await interaction.response.send_modal(CandidatureModal())


class RecruiterAssignmentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TakeTicketButton())
        self.add_item(UnassignTicketButton())
        self.add_item(RecruitButton())
        self.add_item(CloseTicketButton())


class TakeTicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Prendre en charge",
            emoji="👤",
            style=discord.ButtonStyle.success,
            custom_id="cfr:take_ticket"
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.channel:
            return

        cfg = get_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message(
                "La configuration du bot est introuvable.",
                ephemeral=True
            )
            return

        recruiter_role = interaction.guild.get_role(cfg[1])
        if not recruiter_role or recruiter_role not in interaction.user.roles:
            await interaction.response.send_message(
                "Seuls les membres ayant le rôle Recruteur peuvent prendre une candidature en charge.",
                ephemeral=True
            )
            return

        assigned_id = get_ticket_assignment(interaction.channel.id)

        if assigned_id:
            assigned_member = interaction.guild.get_member(assigned_id)
            assigned_name = assigned_member.mention if assigned_member else f"<@{assigned_id}>"
            await interaction.response.send_message(
                f"⚠️ Cette candidature est déjà prise en charge par {assigned_name}.",
                ephemeral=True
            )
            return

        assign_ticket(interaction.channel.id, interaction.user.id)

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} a pris cette candidature en charge."
        )

        await interaction.channel.send(
            f"👤 **Recruteur assigné :** {interaction.user.mention}"
        )


class RecruitButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Donner le rôle Recrue",
            emoji="🎖️",
            style=discord.ButtonStyle.primary,
            custom_id="cfr:give_recrue"
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.channel:
            return

        cfg = get_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message(
                "La configuration du bot est introuvable.",
                ephemeral=True
            )
            return

        recruiter_role = interaction.guild.get_role(cfg[1])
        if not recruiter_role or recruiter_role not in interaction.user.roles:
            await interaction.response.send_message(
                "Seuls les membres ayant le rôle Recruteur peuvent attribuer le rôle Recrue.",
                ephemeral=True
            )
            return

        assigned_id = get_ticket_assignment(interaction.channel.id)
        if assigned_id != interaction.user.id:
            if assigned_id:
                assigned_member = interaction.guild.get_member(assigned_id)
                assigned_name = assigned_member.mention if assigned_member else f"<@{assigned_id}>"
                message = (
                    f"⚠️ Cette candidature est assignée à {assigned_name}. "
                    "Seul le recruteur assigné peut attribuer le rôle Recrue."
                )
            else:
                message = (
                    "⚠️ Tu dois d'abord prendre cette candidature en charge "
                    "avant de pouvoir attribuer le rôle Recrue."
                )
            await interaction.response.send_message(message, ephemeral=True)
            return

        candidate_id = get_ticket_candidate(interaction.channel.id)
        if candidate_id is None:
            await interaction.response.send_message(
                "Impossible de retrouver le candidat associé à ce ticket.",
                ephemeral=True
            )
            return

        candidate = interaction.guild.get_member(candidate_id)
        if candidate is None:
            try:
                candidate = await interaction.guild.fetch_member(candidate_id)
            except discord.NotFound:
                await interaction.response.send_message(
                    "Le candidat n'est plus présent sur le serveur.",
                    ephemeral=True
                )
                return
            except discord.HTTPException:
                await interaction.response.send_message(
                    "Impossible de retrouver le candidat pour le moment.",
                    ephemeral=True
                )
                return

        # Le rôle est volontairement recherché par son nom pour ne pas ajouter
        # de nouvelle configuration à /config.
        recrue_role = discord.utils.get(interaction.guild.roles, name="Recrue")
        if recrue_role is None:
            await interaction.response.send_message(
                "Le rôle **Recrue** n'existe pas sur ce serveur. Crée-le d'abord.",
                ephemeral=True
            )
            return

        if recrue_role in candidate.roles:
            await interaction.response.send_message(
                f"ℹ️ {candidate.mention} possède déjà le rôle **Recrue**.",
                ephemeral=True
            )
            return

        try:
            await candidate.add_roles(
                recrue_role,
                reason=f"Candidature CFr acceptée par {interaction.user}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Je ne peux pas attribuer le rôle **Recrue**. "
                "Vérifie que le rôle est placé sous le rôle du bot dans la hiérarchie Discord.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"🎖️ {candidate.mention} reçoit maintenant le rôle **Recrue**. "
            f"Candidature validée par {interaction.user.mention}."
        )


class UnassignTicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Se désassigner",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            custom_id="cfr:unassign_ticket"
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.channel:
            return

        cfg = get_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message(
                "La configuration du bot est introuvable.",
                ephemeral=True
            )
            return

        recruiter_role = interaction.guild.get_role(cfg[1])
        if not recruiter_role or recruiter_role not in interaction.user.roles:
            await interaction.response.send_message(
                "Seuls les membres ayant le rôle Recruteur peuvent se désassigner.",
                ephemeral=True
            )
            return

        assigned_id = get_ticket_assignment(interaction.channel.id)

        if assigned_id is None:
            await interaction.response.send_message(
                "Cette candidature n'est actuellement assignée à personne.",
                ephemeral=True
            )
            return

        if assigned_id != interaction.user.id:
            assigned_member = interaction.guild.get_member(assigned_id)
            assigned_name = assigned_member.mention if assigned_member else f"<@{assigned_id}>"
            await interaction.response.send_message(
                f"⚠️ Cette candidature est assignée à {assigned_name}. "
                f"Seul ce recruteur peut se désassigner.",
                ephemeral=True
            )
            return

        unassign_ticket(interaction.channel.id)

        await interaction.response.send_message(
            f"🔄 {interaction.user.mention} s'est désassigné de cette candidature."
        )


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CloseTicketButton())


class CloseTicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Archiver le ticket",
            emoji="📁",
            style=discord.ButtonStyle.danger,
            custom_id="cfr:close_ticket"
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.channel:
            return

        cfg = get_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message(
                "La configuration du bot est introuvable.",
                ephemeral=True
            )
            return

        recruiter_role = interaction.guild.get_role(cfg[1])
        if not recruiter_role or recruiter_role not in interaction.user.roles:
            await interaction.response.send_message(
                "Seuls les membres ayant le rôle Recruteur peuvent archiver un ticket.",
                ephemeral=True
            )
            return

        archive_category = interaction.guild.get_channel(cfg[3]) if len(cfg) > 3 and cfg[3] else None
        if not archive_category or not isinstance(archive_category, discord.CategoryChannel):
            await interaction.response.send_message(
                "La catégorie d'archives n'est pas configurée. "
                "Utilise `/config` avec une catégorie d'archives.",
                ephemeral=True
            )
            return

        candidate_id = get_ticket_candidate(interaction.channel.id)
        candidate = interaction.guild.get_member(candidate_id) if candidate_id else None

        # Retire l'accès du candidat.
        if candidate:
            await interaction.channel.set_permissions(
                candidate,
                view_channel=False,
                send_messages=False,
                read_message_history=False,
                reason="Candidature archivée"
            )

        # Archive en lecture seule pour les recruteurs.
        await interaction.channel.set_permissions(
            recruiter_role,
            view_channel=True,
            send_messages=False,
            read_message_history=True,
            reason="Candidature archivée"
        )

        await interaction.channel.set_permissions(
            interaction.guild.me,
            view_channel=True,
            send_messages=False,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
            reason="Candidature archivée"
        )

        new_name = interaction.channel.name
        if not new_name.startswith("archive-"):
            base = new_name[len("recruteur-"):] if new_name.startswith("recruteur-") else new_name
            new_name = f"archive-{base}"[:100]

        await interaction.channel.edit(
            name=new_name,
            category=archive_category,
            reason=f"Candidature archivée par {interaction.user}"
        )

        # Le ticket n'est plus actif : le candidat pourra déposer une nouvelle candidature.
        unassign_ticket(interaction.channel.id)
        clear_ticket_candidate(interaction.channel.id)

        await interaction.response.send_message(
            f"📁 **Candidature archivée par {interaction.user.mention}.**\n"
            "Le ticket a été déplacé dans les archives et est maintenant en lecture seule."
        )



class CFrBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(WelcomeView())
        self.add_view(RecruiterAssignmentView())
        self.add_view(CloseTicketView())

        # Synchronisation globale des commandes.
        await self.tree.sync()

        # Synchronisation immédiate sur les serveurs déjà configurés.
        # Cela permet notamment à /config d'afficher immédiatement
        # le nouveau paramètre "archives", sans attendre la propagation
        # de Discord (qui peut prendre du temps en global).
        conn = db()
        guild_ids = [
            row[0]
            for row in conn.execute("SELECT guild_id FROM config").fetchall()
        ]
        conn.close()

        for guild_id in guild_ids:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            try:
                await self.tree.sync(guild=guild)
                print(f"Commandes synchronisées sur le serveur {guild_id}.")
            except discord.HTTPException as exc:
                print(f"Impossible de synchroniser les commandes sur {guild_id}: {exc}")


bot = CFrBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    db().close()
    print(f"Connecté en tant que {bot.user} (ID {bot.user.id})")


@bot.tree.command(name="config", description="Configure le système CFr.")
@app_commands.describe(
    presentation="Salon où les membres font leur présentation/candidature",
    recruteur="Rôle qui doit voir les tickets",
    categorie="Catégorie Discord où créer les tickets (optionnel)",
    archives="Catégorie Discord où déplacer les tickets terminés"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def config(
    interaction: discord.Interaction,
    presentation: discord.TextChannel,
    recruteur: discord.Role,
    categorie: discord.CategoryChannel | None = None,
    archives: discord.CategoryChannel | None = None
):
    set_config(
        interaction.guild.id,
        presentation.id,
        recruteur.id,
        categorie.id if categorie else None,
        archives.id if archives else None
    )
    await interaction.response.send_message(
        f"Configuration enregistrée.\n"
        f"• Présentation : {presentation.mention}\n"
        f"• Recruteurs : {recruteur.mention}\n"
        f"• Catégorie tickets : {categorie.mention if categorie else 'aucune'}\n"
        f"• Archives : {archives.mention if archives else 'aucune'}",
        ephemeral=True
    )


async def _archive_ticket(interaction: discord.Interaction, accepted: bool):
    if not interaction.guild or not interaction.channel:
        return

    cfg = get_config(interaction.guild.id)
    if not cfg:
        await interaction.response.send_message(
            "La configuration du bot est introuvable.",
            ephemeral=True
        )
        return

    recruiter_role = interaction.guild.get_role(cfg[1])
    if not recruiter_role or recruiter_role not in interaction.user.roles:
        await interaction.response.send_message(
            "⛔ Seuls les membres ayant le rôle **Recruteur** peuvent archiver une candidature.",
            ephemeral=True
        )
        return

    archive_category = interaction.guild.get_channel(cfg[3]) if len(cfg) > 3 and cfg[3] else None
    if not archive_category or not isinstance(archive_category, discord.CategoryChannel):
        await interaction.response.send_message(
            "⚠️ La catégorie d'archives n'est pas configurée. Configure-la avec `/config`.",
            ephemeral=True
        )
        return

    candidate_id = get_ticket_candidate(interaction.channel.id)
    if candidate_id is None:
        await interaction.response.send_message(
            "⚠️ Ce salon ne semble pas être un ticket de candidature.",
            ephemeral=True
        )
        return

    candidate = interaction.guild.get_member(candidate_id)

    try:
        if accepted:
            if candidate is None:
                try:
                    candidate = await interaction.guild.fetch_member(candidate_id)
                except discord.NotFound:
                    await interaction.response.send_message(
                        "⚠️ Le candidat n'est plus présent sur le serveur.",
                        ephemeral=True
                    )
                    return

            recrue_role = discord.utils.get(interaction.guild.roles, name="Recrue")
            if recrue_role is None:
                await interaction.response.send_message(
                    "⚠️ Le rôle **Recrue** n'existe pas sur ce serveur. Crée-le d'abord.",
                    ephemeral=True
                )
                return

            if recrue_role not in candidate.roles:
                try:
                    await candidate.add_roles(
                        recrue_role,
                        reason=f"Candidature CFr validée par {interaction.user}"
                    )
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "❌ Je ne peux pas attribuer le rôle **Recrue**. "
                        "Vérifie que le rôle est placé sous le rôle du bot.",
                        ephemeral=True
                    )
                    return

        if candidate:
            await interaction.channel.set_permissions(
                candidate,
                view_channel=False,
                send_messages=False,
                read_message_history=False,
                reason="Candidature archivée"
            )

        await interaction.channel.set_permissions(
            recruiter_role,
            view_channel=True,
            send_messages=False,
            read_message_history=True,
            reason="Candidature archivée"
        )

        await interaction.channel.set_permissions(
            interaction.guild.me,
            view_channel=True,
            send_messages=False,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
            reason="Candidature archivée"
        )

        current_name = interaction.channel.name
        if current_name.startswith("recruteur-"):
            base_name = current_name[len("recruteur-"):]
        elif current_name.startswith("archive-"):
            base_name = current_name[len("archive-"):]
        elif current_name.startswith("validee-"):
            base_name = current_name[len("validee-"):]
        elif current_name.startswith("refusee-"):
            base_name = current_name[len("refusee-"):]
        else:
            base_name = current_name

        prefix = "validee-" if accepted else "refusee-"
        new_name = f"{prefix}{base_name}"[:100]

        await interaction.channel.edit(
            name=new_name,
            category=archive_category,
            reason=f"Candidature {'validée' if accepted else 'refusée'} par {interaction.user}"
        )

        unassign_ticket(interaction.channel.id)
        clear_ticket_candidate(interaction.channel.id)

        if accepted:
            message = (
                f"🎖️ **Candidature validée par {interaction.user.mention}.**\n"
                f"{candidate.mention if candidate else 'Le candidat'} reçoit le rôle **Recrue**.\n"
                f"📁 Ticket déplacé dans {archive_category.mention}."
            )
        else:
            message = (
                f"❌ **Candidature refusée par {interaction.user.mention}.**\n"
                f"📁 Ticket déplacé dans {archive_category.mention}."
            )

        await interaction.response.send_message(message)

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Je n'ai pas les permissions nécessaires pour cette opération.",
            ephemeral=True
        )
    except discord.HTTPException as exc:
        await interaction.response.send_message(
            f"❌ Discord a refusé l'opération : `{exc}`",
            ephemeral=True
        )


@bot.tree.command(name="archive_validee", description="Valide et archive la candidature actuelle.")
async def archive_validee(interaction: discord.Interaction):
    await _archive_ticket(interaction, accepted=True)


@bot.tree.command(name="archive_refusee", description="Refuse et archive la candidature actuelle.")
async def archive_refusee(interaction: discord.Interaction):
    await _archive_ticket(interaction, accepted=False)


@bot.tree.command(name="welcome", description="Publie le message de bienvenue CFr avec les boutons.")
@app_commands.checks.has_permissions(manage_guild=True)
async def welcome(interaction: discord.Interaction):
    if not get_config(interaction.guild.id):
        await interaction.response.send_message(
            "Configure d'abord le bot avec `/config`.",
            ephemeral=True
        )
        return

    await interaction.channel.send(content=WELCOME_TEXT, view=WelcomeView())
    await interaction.response.send_message(
        "Message de bienvenue publié. ✅",
        ephemeral=True
    )


@bot.event
async def on_message(message: discord.Message):
    # Les candidatures sont maintenant traitées directement par le formulaire.
    # On conserve on_message uniquement pour que les commandes préfixées
    # éventuelles continuent de fonctionner.
    if not message.author.bot:
        await bot.process_commands(message)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        message = "Tu dois avoir la permission **Gérer le serveur** pour utiliser cette commande."
    else:
        message = f"Une erreur est survenue : `{error}`"

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError(
            "Variable DISCORD_TOKEN absente. Configure-la avant de lancer bot.py."
        )
    bot.run(token)
    
