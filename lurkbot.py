import discord
import requests
import asyncio
import json
import os
import re
from discord.ext import tasks, commands
from html import unescape

DISCORD_BOT_TOKEN = ''

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Enable the Server Members Intent
bot = commands.Bot(command_prefix='!', intents=intents)

tracked_thread = {}
dm_users = []
update_channels = []
last_post = {}

# JSON data handling functions
def load_data():
    global tracked_thread, dm_users, update_channels
    if os.path.exists('data.json'):
        with open('data.json', 'r') as f:
            data = json.load(f)
            tracked_thread = data.get('tracked_thread', {})
            dm_users = data.get('dm_users', [])
            update_channels = data.get('update_channels', [])
            # Ensure post_count is initialized
            if 'post_count' not in tracked_thread:
                tracked_thread['post_count'] = 0
    else:
        tracked_thread = {}
        dm_users = []
        update_channels = []

def save_data():
    with open('data.json', 'w') as f:
        json.dump({'tracked_thread': tracked_thread, 'dm_users': dm_users, 'update_channels': update_channels}, f)

def clean_html(raw_html):
    clean_text = re.sub(r'<.*?>', '', raw_html)
    return unescape(clean_text)

def format_post_content(post, board, thread_id):
    raw_content = post.get("com", "No content")
    # Separate out reply links and format them as hyperlinks
    reply_links = re.findall(r'(&gt;&gt;\d+)', raw_content)
    for reply_link in reply_links:
        post_id = reply_link[8:]
        url = create_reply_links(board, thread_id, post_id)
        # Ensure there's a space after the reply link if not already present
        raw_content = re.sub(r'{}(?!\s)'.format(re.escape(reply_link)), f'{reply_link} ', raw_content)
        raw_content = raw_content.replace(reply_link, f'[{reply_link}]({url})')
    content = clean_html(raw_content)
    return content

def create_reply_links(board, thread_id, post_id):
    base_url = f"https://boards.4chan.org/{board}/thread/{thread_id}#p{post_id}"
    return base_url

async def notify_users(embed):
    for user_id in dm_users:
        user = await bot.fetch_user(user_id)
        await user.send(embed=embed)

async def notify_channels(embed):
    for channel_id in update_channels:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)

async def send_notification(embed, inform_users=True, inform_channels=True):
    if inform_users:
        await notify_users(embed)
    if inform_channels:
        await notify_channels(embed)

@bot.event
async def on_ready():
    load_data()
    print(f'Logged in as {bot.user}')
    await send_notification(discord.Embed(title="Bot Restarted", description="The bot has been restarted.", color=discord.Color.green()))
    check_thread.start()

@bot.command()
async def track(ctx, thread_url: str):
    """Command to start tracking a 4chan thread."""
    parts = thread_url.split('/')
    board = parts[3]
    thread_id = parts[5]
    
    # Get the current last post number to avoid fetching all previous posts as new
    url = f'https://a.4cdn.org/{board}/thread/{thread_id}.json'
    response = requests.get(url)
    if response.status_code == 200:
        thread_data = response.json()
        last_post_num = thread_data['posts'][-1]['no'] if thread_data['posts'] else None

        global tracked_thread
        tracked_thread = {
            'board': board,
            'thread_id': thread_id,
            'last_post_num': last_post_num,
            'notified_450': False,
            'notified_500': False,
            'post_count': len(thread_data['posts']) if thread_data['posts'] else 0
        }
        save_data()
        await ctx.send(f'Started tracking thread: {thread_url}')
        
        embed = discord.Embed(title="New Thread Tracking", description=f"Started tracking thread: {thread_url}", color=discord.Color.green())
        await send_notification(embed)
    else:
        await ctx.send(f'Failed to start tracking thread: {thread_url}')
        embed = discord.Embed(title="Error", description=f"Failed to start tracking thread: {thread_url}", color=discord.Color.red())
        await send_notification(embed)

@bot.command()
async def add_user(ctx, user: discord.User):
    """Command to add a user to the DM list."""
    if user.id not in dm_users:
        dm_users.append(user.id)
        save_data()
        await ctx.send(f'{user.name} has been added to the DM list.')

@bot.command()
async def remove_user(ctx, user: discord.User):
    """Command to remove a user from the DM list."""
    if user.id in dm_users:
        dm_users.remove(user.id)
        save_data()
        await ctx.send(f'{user.name} has been removed from the DM list.')

@bot.command()
async def add_channel(ctx, channel: discord.TextChannel):
    """Command to add a channel to the update list."""
    if channel.id not in update_channels:
        update_channels.append(channel.id)
        save_data()
        await ctx.send(f'Channel {channel.name} has been added to the update list.')

@bot.command()
async def remove_channel(ctx, channel: discord.TextChannel):
    """Command to remove a channel from the update list."""
    if channel.id in update_channels:
        update_channels.remove(channel.id)
        save_data()
        await ctx.send(f'Channel {channel.name} has been removed from the update list.')

@bot.command()
async def bot_status(ctx):
    """Command to check the status of the bot."""
    status = "working" if check_thread.is_running() else "not working"
    embed = discord.Embed(title="Bot Status", description=f"The bot is currently {status}.", color=discord.Color.green() if status == "working" else discord.Color.red())
    await ctx.send(embed=embed)

@bot.command()
async def repost_last(ctx):
    """Command to repost the last tracked post."""
    if last_post:
        embed = discord.Embed(title=last_post['title'], description=last_post['description'], color=last_post['color'])
        embed.add_field(name="Post Link", value=last_post['url'], inline=False)
        if 'image_url' in last_post:
            embed.set_image(url=last_post['image_url'])
        embed.set_footer(text=last_post['footer'])
        await ctx.send(embed=embed)
    else:
        await ctx.send("No last post to repost.")

@bot.command()
async def remove_thread(ctx):
    """Command to stop tracking the current thread."""
    global tracked_thread
    tracked_thread = {}
    save_data()
    await ctx.send("Stopped tracking the current thread.")

@tasks.loop(minutes=1)
async def check_thread():
    try:
        if 'thread_id' not in tracked_thread or 'board' not in tracked_thread:
            return

        board = tracked_thread['board']
        thread_id = tracked_thread['thread_id']
        url = f'https://a.4cdn.org/{board}/thread/{thread_id}.json'
        response = requests.get(url)
        print(f'Fetching URL: {url}')  # Debugging: log the URL being requested
        print(f'Status Code: {response.status_code}')  # Debugging: log the status code

        if response.status_code == 200:
            thread_data = response.json()
            last_post_num = tracked_thread['last_post_num']
            new_posts = []

            for post in thread_data['posts']:
                if last_post_num is None or post['no'] > last_post_num:
                    new_posts.append(post)

            if new_posts:
                tracked_thread['last_post_num'] = new_posts[-1]['no']
                tracked_thread['post_count'] = len(thread_data['posts'])  # Update post count based on total posts in the thread
                save_data()
                for user_id in dm_users:
                    user = await bot.fetch_user(user_id)
                    for post in new_posts:
                        content = format_post_content(post, board, thread_id)
                        reply_link = create_reply_links(board, thread_id, post['no'])
                        post_number = thread_data['posts'].index(post) + 1  # Calculate post number based on its index in the thread
                        color = discord.Color.blue()
                        if post_number >= 450:
                            color = discord.Color.orange()
                        if post_number >= 500:
                            color = discord.Color.red()
                        embed = discord.Embed(title=f"New post in /{board}/ thread {thread_id}",
                                              description=content,
                                              color=color,
                                              url=reply_link)
                        embed.add_field(name="Post Link", value=f"[Go to Post]({reply_link})", inline=False)
                        if 'tim' in post and 'ext' in post:
                            image_url = f'https://i.4cdn.org/{board}/{post["tim"]}{post["ext"]}'
                            embed.set_image(url=image_url)
                        embed.set_footer(text=f"Post ID: {post['no']} • Post Number: {post_number}")
                        await user.send(embed=embed)
                        # Store the last post for reposting
                        last_post['title'] = embed.title
                        last_post['description'] = embed.description
                        last_post['color'] = embed.color
                        last_post['url'] = embed.fields[0].value
                        if 'tim' in post and 'ext' in post:
                            last_post['image_url'] = image_url
                        last_post['footer'] = embed.footer.text

                if not tracked_thread['notified_450'] and len(thread_data['posts']) >= 450:
                    tracked_thread['notified_450'] = True
                    save_data()
                    embed = discord.Embed(title=f"Thread /{board}/ {thread_id} Notification",
                                          description="Thread has reached 450 posts.",
                                          color=discord.Color.orange())
                    await send_notification(embed)

                if not tracked_thread['notified_500'] and len(thread_data['posts']) >= 500:
                    tracked_thread['notified_500'] = True
                    save_data()
                    embed = discord.Embed(title=f"Thread /{board}/ {thread_id} Notification",
                                          description="Thread has reached 500 posts.",
                                          color=discord.Color.red())
                    await send_notification(embed)
        else:
            embed = discord.Embed(title="Error", description=f"Failed to retrieve thread {thread_id} with status code {response.status_code}", color=discord.Color.red())
            await send_notification(embed)

    except Exception as e:
        embed = discord.Embed(title="Bot Error", description=str(e), color=discord.Color.red())
        await send_notification(embed)

bot.run(DISCORD_BOT_TOKEN)
