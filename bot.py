import bot
import requests
import asyncio
import json
import os
from discord.ext import tasks, commands

DISCORD_BOT_TOKEN = 'token'

intents = bot.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

tracked_thread = {}
dm_users = []

# JSON data handling functions
def load_data():
    global tracked_thread, dm_users
    if os.path.exists('data.json'):
        with open('data.json', 'r') as f:
            data = json.load(f)
            tracked_thread = data.get('tracked_thread', {})
            dm_users = data.get('dm_users', [])
    else:
        tracked_thread = {}
        dm_users = []

def save_data():
    with open('data.json', 'w') as f:
        json.dump({'tracked_thread': tracked_thread, 'dm_users': dm_users}, f)

@bot.event
async def on_ready():
    load_data()
    print(f'Logged in as {bot.user}')
    check_thread.start()

@bot.command()
async def track(ctx, thread_url: str):
    """Command to start tracking a 4chan thread."""
    thread_id = thread_url.split('/')[-1].split('.')[0]
    global tracked_thread
    tracked_thread = {
        'thread_id': thread_id,
        'last_post_num': None,
        'notified_450': False,
        'notified_500': False
    }
    save_data()
    await ctx.send(f'Started tracking thread: {thread_url}')

@bot.command()
async def add_user(ctx, user: bot.User):
    """Command to add a user to the DM list."""
    if user.id not in dm_users:
        dm_users.append(user.id)
        save_data()
        await ctx.send(f'{user.name} has been added to the DM list.')

@tasks.loop(minutes=3)
async def check_thread():
    if 'thread_id' not in tracked_thread:
        return

    thread_id = tracked_thread['thread_id']
    url = f'https://a.4cdn.org/thread/{thread_id}.json'
    response = requests.get(url)
    if response.status_code == 200:
        thread_data = response.json()
        last_post_num = tracked_thread['last_post_num']
        new_posts = []

        for post in thread_data['posts']:
            if last_post_num is None or post['no'] > last_post_num:
                new_posts.append(post)

        if new_posts:
            tracked_thread['last_post_num'] = new_posts[-1]['no']
            save_data()
            for user_id in dm_users:
                user = await bot.fetch_user(user_id)
                for post in new_posts:
                    await user.send(f'New post in thread {thread_id}: {post.get("com", "No content")}')

        if not tracked_thread['notified_450'] and len(thread_data['posts']) >= 450:
            tracked_thread['notified_450'] = True
            save_data()
            for user_id in dm_users:
                user = await bot.fetch_user(user_id)
                await user.send(f'Thread {thread_id} has reached 450 posts.')

        if not tracked_thread['notified_500'] and len(thread_data['posts']) >= 500:
            tracked_thread['notified_500'] = True
            save_data()
            for user_id in dm_users:
                user = await bot.fetch_user(user_id)
                await user.send(f'Thread {thread_id} has reached 500 posts.')
    else:
        print(f'Failed to retrieve thread {thread_id}')

bot.run(DISCORD_BOT_TOKEN)
