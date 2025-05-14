import discord
from discord.ext import commands
from discord.ui import View, Button
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH")

app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

registered_teams = {}

def add_team_to_sheet(team_name, team_members):
    try:
        print("🔄 Connecting to Google Sheets...")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_PATH, scope)
        client = gspread.authorize(creds)

        sheet = client.open("CarrotG").worksheet("Valorant Teams Data")

        # 🔍 Check for duplicate tags
        existing = sheet.get_all_values()[1:]  # skip header row
        saved_tags = set()
        for row in existing:
            saved_tags.update(row[2::2])  # tags are in every second column starting from index 2

        for member in team_members:
            if member["tag"] in saved_tags:
                print(f"❌ Duplicate found: {member['tag']}")
                return False  # Signal to the bot that save should be skipped

        # ✅ No duplicates → Save
        row = [team_name]
        for member in team_members:
            row.append(member["name"])
            row.append(member["tag"])

        sheet.append_row(row)
        print(f"✅ Team '{team_name}' saved to Google Sheet.")
        return True

    except Exception as e:
        print("❌ Failed to write to Google Sheet:", e)
        return False

# 👇 Define your view first
class RegisterView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RegisterButton())

class RegisterButton(Button):
    def __init__(self):
        super().__init__(label="Register", style=discord.ButtonStyle.blurple, emoji="📩", custom_id="register_button")

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        try:
            await user.send("👋 Hi! Let's get your team registered.")
            await user.send("📝 What's your **team name**?")

            def check_self(m):
                return m.author == user and isinstance(m.channel, discord.DMChannel)

            # 🟩 Connect to Google Sheets to check for existing team names
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_PATH, scope)
            client = gspread.authorize(creds)
            sheet = client.open("CarrotG").worksheet("Valorant Teams Data")
            existing_team_names = [row[0].strip().lower() for row in sheet.get_all_values()[1:] if row]

            # 🔁 Ask until unique team name is given
            while True:
                team_msg = await bot.wait_for("message", check=check_self, timeout=60.0)
                team_name = team_msg.content.strip()
                if team_name.lower() in existing_team_names:
                    await user.send("⚠️ A team with this name already exists. Please choose another team name.")
                else:
                    break


            team_members = []

            # 👤 Player 1 (button clicker)
            await user.send("👤 Your full name:")
            name1 = (await bot.wait_for("message", check=check_self, timeout=60.0)).content.strip()

            await user.send("🔖 Your Discord tag (e.g., PewPew#1234):")
            tag1 = (await bot.wait_for("message", check=check_self, timeout=60.0)).content.strip()

            team_members.append({"name": name1, "tag": tag1})

            # 👥 Players 2–5
            for i in range(2, 6):
                await user.send(f"👤 Enter full name for Player {i}:")
                name = (await bot.wait_for("message", check=check_self, timeout=60.0)).content.strip()

                await user.send(f"🔖 Enter Discord tag for Player {i} (e.g., PewPew#1234):")
                tag = (await bot.wait_for("message", check=check_self, timeout=60.0)).content.strip()

                team_members.append({"name": name, "tag": tag})

            def format_team(members):
                return "\n\n".join([f"Player {i+1}\nName: {m['name']}\nUsername: {m['tag']}" for i, m in enumerate(members)])

            # 🔁 Allow editing
            while True:
                members_formatted = format_team(team_members)
                await user.send(
                    f"📋 Here’s your current team:\n\n"
                    f"**Team Name:** {team_name}\n\n"
                    f"{members_formatted}"
                )

                await user.send("✏️ Do you want to edit any player? (yes/no)")
                answer = (await bot.wait_for("message", check=check_self, timeout=60.0)).content.strip().lower()

                if answer in ["no", "n"]:
                    break
                elif answer in ["yes", "y"]:
                    await user.send("🔢 Enter the number of the player you want to edit (1-5):")
                    try:
                        num = int((await bot.wait_for("message", check=check_self, timeout=60.0)).content.strip())
                        if not 1 <= num <= 5:
                            await user.send("❌ Invalid number. Please enter 1 to 5.")
                            continue

                        await user.send(f"👤 New name for Player {num}:")
                        new_name = (await bot.wait_for("message", check=check_self, timeout=60.0)).content.strip()

                        await user.send(f"🔖 New tag for Player {num}:")
                        new_tag = (await bot.wait_for("message", check=check_self, timeout=60.0)).content.strip()

                        team_members[num - 1] = {"name": new_name, "tag": new_tag}
                        await user.send("✅ Player updated!")

                    except Exception:
                        await user.send("❌ Invalid input. Try again.")
                else:
                    await user.send("❓ Please answer with `yes` or `no`.")

            # ✅ Save final team
            registered_teams[user.id] = {
                "team_name": team_name,
                "members": team_members
            }
            saved = add_team_to_sheet(team_name, team_members)
            if saved:
                await user.send("✅ Final team saved! Thank you for registering.")
                await interaction.response.send_message("✅ Check your DMs! Team registration completed.", ephemeral=True)
            else:
                await user.send("❌ A player in this team is already registered. Please double-check your players.")
                await interaction.response.send_message("⚠️ Registration canceled due to duplicate player.", ephemeral=True)


        except Exception as e:
            print("Error in registration:", e)
            await interaction.response.send_message("❌ Could not send DM. Please enable DMs from server members.", ephemeral=True)

# 🧷 Command to send the registration button
@bot.command()
async def setup_ticket(ctx):
    await ctx.send("🎫 Click below to register your team:", view=RegisterView())

# 🟢 Register the button view when the bot starts
@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")
    bot.add_view(RegisterView())

keep_alive()
# Run the bot using your token
bot.run(DISCORD_BOT_TOKEN)

