import discord
from discord.ext import commands
from discord.utils import get
import youtube_dl
import asyncio
from functools import partial
from async_timeout import timeout
import itertools
import requests


# token
import os
from dotenv import load_dotenv
load_dotenv()
token = os.getenv('TOKEN')
# token


bot = commands.Bot(command_prefix = "-",help_command = None)

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' 
}

FFMPEG_OPTIONS = {
    'options': '-vn',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"}


def GET_BTC_PRICE():
    data = requests.get('https://bx.in.th/api/')
    BTC_PRICE = data.text.split('BTC')[1].split('last_price":')[1].split(',"volume_24hours')[0]
    return BTC_PRICE

API_URL = 'https://api.bitkub.com'

endpoint = {
    'status':'/api/status',
    'timestamp':'/api/servertime',
    'symbols':'/api/market/symbols',
    'ticker':'/api/market/ticker',
    'trades':'/api/market/trades'

}

def GET_BTC_PRICE_02(COIN = 'THB_BTC'):
    url = API_URL + endpoint['ticker']
    r = requests.get(url,params = {'sym':COIN})
    data = r.json()
    PRICE_BTC = data[COIN]['last']
    return PRICE_BTC


ytdl = youtube_dl.YoutubeDL(YDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):

    def __init__(self, source, *, data, requester):
        super().__init__(source)
        self.requester = requester

        self.title = data.get('title')
        self.web_url = data.get('webpage_url')



    def __getitem__(self, item: str):

        return self.__getattribute__(item)

    @classmethod
    async def create_source(cls, ctx, search: str, *, loop, download=False):
        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl.extract_info, url=search, download=download)
        data = await loop.run_in_executor(None, to_run)

        if 'entries' in data:

            data = data['entries'][0]

        await ctx.send(f'```ini\n[Added {data["title"]} to the Queue.]\n```')
        if download:
            source = ytdl.prepare_filename(data)
        else:
            return {'webpage_url': data['webpage_url'], 'requester': ctx.author, 'title': data['title']}

        return cls(discord.FFmpegPCMAudio(source, **FFMPEG_OPTIONS), data=data, requester=ctx.author)

    @classmethod
    async def regather_stream(cls, data, *, loop):
        loop = loop or asyncio.get_event_loop()
        requester = data['requester']

        to_run = partial(ytdl.extract_info, url=data['webpage_url'], download=False)
        data = await loop.run_in_executor(None, to_run)

        return cls(discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS), data=data, requester=requester)

class MusicPlayer:

    __slots__ = ('bot', '_guild', '_channel', '_cog', 'queue', 'next', 'current', 'np', 'volume')

    def __init__(self, ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.np = None
        self.volume = .5
        self.current = None

        ctx.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            try:

                async with timeout(3600): # 1 hr
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                # del players[self._guild]
                return await self.destroy(self._guild)

            if not isinstance(source, YTDLSource):

                try:
                    source = await YTDLSource.regather_stream(source, loop=self.bot.loop)
                except Exception as e:
                    await self._channel.send(f'There was an error processing your song.\n'
                                             f'```css\n[{e}]\n```')
                    continue

            source.volume = self.volume
            self.current = source

            self._guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            self.np = await self._channel.send(f'**Now Playing:** `{source.title}` requested by '
                                               f'`{source.requester}`')
            await self.next.wait()


            source.cleanup()
            self.current = None

            try:

                await self.np.delete()
            except discord.HTTPException:
                pass

    async def destroy(self, guild):

        # del players[self._guild]
        await self._guild.voice_client.disconnect()
        return self.bot.loop.create_task(self._cog.cleanup(guild))

@bot.event
async def on_ready():
    print(f'Origami online !\n{bot.user}')


@bot.command()
async def write(ctx,msg):
    await ctx.channel.send(msg)




@bot.command()
async def play(ctx, url):
    channel = ctx.author.voice.channel
    voice_client = get(bot.voice_clients, guild=ctx.guild)

    if voice_client == None:
        await ctx.channel.send('Joined')
        await channel.connect()
        voice_client = get(bot.voice_clients, guild=ctx.guild)



    if not voice_client.is_playing():
        with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)

        URL = info['formats'][0]['url']
        voice_client.play(discord.FFmpegPCMAudio(URL, **FFMPEG_OPTIONS))
        voice_client.is_playing()
    else:
        await ctx.channel.send('ตอนนี้กำลังเปิดเพลงอื่นอยู่...\nขณะนี้ผู้พัฒนาได้เพิ่มระบบคิวแล้วสามารถดูวิธีใช้ได้โดยพิมพ์ -help')
        return

@bot.command()
async def p(ctx,* ,search: str):
    channel = ctx.author.voice.channel
    voice_client = get(bot.voice_clients, guild=ctx.guild)

    if voice_client == None:
        await ctx.channel.send('Joined')
        await channel.connect()
        voice_client = get(bot.voice_clients, guild=ctx.guild)
    
    await ctx.trigger_typing()

    _player = get_player(ctx)
    source = await YTDLSource.create_source(ctx, search, loop=bot.loop, download=False)
    await _player.queue.put(source)


players = {}
def get_player(ctx):
    try:
        player = players[ctx.guild.id]
    except:
        player = MusicPlayer(ctx)
        players[ctx.guild.id] = player

    return player



@bot.command()
async def stop(ctx):
    voice_client = get(bot.voice_clients, guild=ctx.guild)
    if voice_client == None:
        await ctx.channel.send('ตอนนี้ไม่มีเพลงที่เปิดอยู่ไม่สามารถใช้คำสั่ง stop ได้')
        return
    
    if voice_client.channel != ctx.author.voice.channel:
        await ctx.channel.send(f'ขณะนี้กำลังเล่นเพลงอยู่ที่ {voice_client.channel} แต่คุณอยู่ที่ {ctx.author.voice.channel}\nเพื่อไม่ให้เกิดปัญหาจึงไม่อนุญาตให้ใช้คำสั่ง -stop')
        return
    
    voice_client.stop()

@bot.command()
async def pause(ctx):
    voice_client = get(bot.voice_clients, guild=ctx.guild)
    if voice_client == None:
        await ctx.channel.send('ขณะนี้เพลงยังไม่ได้เล่นไม่สามารถ pause ได้')
        return
    
    if voice_client.channel != ctx.author.voice.channel:
        await ctx.channel.send(f'ขณะนี้กำลังเล่นเพลงอยู่ที่ {voice_client.channel} แต่คุณอยู่ที่ {ctx.author.voice.channel}\nเพื่อไม่ให้เกิดปัญหาจึงไม่อนุญาตให้ใช้คำสั่ง -pause')
        return
    
    voice_client.pause()

@bot.command()
async def resume(ctx):
    voice_client = get(bot.voice_clients, guild=ctx.guild)
    if voice_client == None:
        await ctx.channel.send('ขณะนี้ยังไม่มีการเปิดเพลงไม่สามารถ pause ได้')
        return
    
    if voice_client.channel != ctx.author.voice.channel:
        await ctx.channel.send(f'ขณะนี้กำลังเล่นเพลงอยู่ที่ {voice_client.channel} แต่คุณอยู่ที่ {ctx.author.voice.channel}\nเพื่อไม่ให้เกิดปัญหาจึงไม่อนุญาตให้ใช้คำสั่ง -resume')
        return
    
    voice_client.resume()


@bot.command()
async def discon(ctx):

    try:
        del players[ctx.guild.id]
        await ctx.channel.send('Disconnected')
        await ctx.voice_client.disconnect()
    except:
        await ctx.channel.send('Disconnected')
        await ctx.voice_client.disconnect()

@bot.command()
async def qlist(ctx):
    voice_client = get(bot.voice_clients, guild=ctx.guild)
    if voice_client == None:
        await ctx.channel.send('ขณะนี้เพลงยังไม่ได้เปิดไม่สามารถดูคิวได้')
        return
    
    if voice_client.channel != ctx.author.voice.channel:
        await ctx.channel.send(f'ขณะนี้กำลังเล่นเพลงอยู่ที่ {voice_client.channel} แต่คุณอยู่ที่ {ctx.author.voice.channel}\nเพื่อไม่ให้เกิดปัญหาจึงไม่อนุญาตให้ใช้คำสั่ง -qlist')
        return
    
    player = get_player(ctx)
    if player.queue.empty():
        return await ctx.send('ไม่พบคิวเพลง')

    Q_list = list(itertools.islice(player.queue._queue,0,player.queue.qsize()))
    fmt = '\n'.join(f'**`{_["title"]}`**' for _ in Q_list)
    EMBED = discord.Embed(title=f'มีเพลงในคิวอยู่ {len(Q_list)} เพลง', description=fmt,color=0x30ffdd)
    EMBED.set_thumbnail(url='https://data.whicdn.com/images/190625600/original.gif')
    
    await ctx.send(embed=EMBED)

@bot.command()
async def skip(ctx):
    voice_client = get(bot.voice_clients, guild=ctx.guild)
    if voice_client == None:
        await ctx.channel.send('ขณะนี้เพลงยังไม่ได้เปิดไม่สามารถ skip ไม่ได้')
        return
    
    if voice_client.channel != ctx.author.voice.channel:
        await ctx.channel.send(f'ขณะนี้กำลังเล่นเพลงอยู่ที่ {voice_client.channel} แต่คุณอยู่ที่ {ctx.author.voice.channel}\nเพื่อไม่ให้เกิดปัญหาจึงไม่อนุญาตให้ใช้คำสั่ง -skip')
        return

    if not voice_client.is_playing():
            return


    voice_client.stop()
    player = get_player(ctx)
    if player.queue.empty():
        await ctx.send(f'เพลงถูก skip โดย **`{ctx.author.name}`**\n**`คำเตือน:`** ขณะนี้ไม่มีเพลงให้ skip แล้ว')
    elif not player.queue.empty():
        await ctx.send(f'เพลงถูก skip โดย **`{ctx.author.name}`**')

@bot.command()
async def help(ctx):
    EMBED = discord.Embed(title='Let Origami help you',description='All command',color=0x9014d9)
    EMBED.add_field(name='-help',value='ใช้คำสั่งนี้เพื่อ{}'.format('ดูคำสั่งทั้งหมดของ Bot'),inline=False)
    EMBED.add_field(name='-write พิมพ์ข้อความ',value='ใช้คำสั่งนี้เพื่อ{}'.format('ให้ Bot พิมพ์ตามคนใช้คำสั่ง'),inline=False)
    EMBED.add_field(name='-join',value='ใช้คำสั่งนี้เพื่อ{}'.format('ให้ Bot เข้ามาในห้อง'),inline=False)
    EMBED.add_field(name='-play link เพลง',value='ใช้คำสั่งนี้เพื่อ{}'.format('ให้ Bot เข้าห้องและเปิดเพลง (ไม่มีระบบคิว)'),inline=False)
    EMBED.add_field(name='-p link เพลง หรือ -p ชื่อเพลง',value='ใช้คำสั่งนี้เพื่อ{}'.format('ให้ Bot เข้าห้องและเปิดเพลง (ระบบคิว)'),inline=False)
    EMBED.add_field(name='-qlist',value='ใช้คำสั่งนี้เพื่อ{}'.format('ดูคิวเพลง'),inline=False)
    EMBED.add_field(name='-skip',value='ใช้คำสั่งนี้เพื่อ{}'.format('สั่งให้ Bot ข้ามเพลง'),inline=False)
    EMBED.add_field(name='-stop',value='ใช้คำสั่งนี้เพื่อ{}'.format('ให้ Bot หยุดเล่นเพลง (เพลงจะจบเลย)'),inline=False)
    EMBED.add_field(name='-pause',value='ใช้คำสั่งนี้เพื่อ{}'.format('ให้ Bot หยุดเล่นเพลง (หยุดเล่นชั่วคราวสามารถ resume ได้)'),inline=False)
    EMBED.add_field(name='-resume',value='ใช้คำสั่งนี้เพื่อ{}'.format('ให้ Bot เล่นเพลงต่อ'),inline=False)
    EMBED.add_field(name='-discon',value='ใช้คำสั่งนี้เพื่อ{}'.format('ให้ Bot ออกจากห้อง'),inline=False)
    EMBED.add_field(name='-btc',value='ใช้คำสั่งนี้เพื่อ{}'.format('ให้ Bot แสดงราคา Bitcoin (ดึงข้อมูลมาจาก bitkub)'),inline=False)
    EMBED.add_field(name='-google keyword 1 + keyword 2 + keyword 3 +...+ kryword n',value='ใช้คำสั่งนี้เพื่อ{}'.format('ให้ Bot Search Google โดยตอนเว้นวรรคให้พิมพ์เครื่องหมาย + แทนการเว้นวรรค'),inline=False)
    EMBED.set_thumbnail(url='https://i.pinimg.com/originals/59/50/f0/5950f0a238dae9016bcbc853feb9726d.gif')
    EMBED.set_footer(text='SaRai (ผู้พัฒนา Bot Origami)',icon_url='https://i.pinimg.com/564x/07/94/23/0794238e1a47395d00e8bb3c8e903d61.jpg')



    
    await ctx.channel.send(embed=EMBED)

@bot.command()
async def join(ctx):
    channel = ctx.author.voice.channel
    voice_client = get(bot.voice_clients, guild=ctx.guild)

    if voice_client == None:
        await ctx.channel.send('Joined')
        await channel.connect()
        voice_client = get(bot.voice_clients, guild=ctx.guild)

@bot.command()
async def btc(ctx):

    msg = f'ราคา Bitcoin ขณะนี้: {GET_BTC_PRICE_02()} บาท'
    EMBED = discord.Embed(title='Bitcoin price from bitkub',description=msg,color=0x42ff21)
    EMBED.set_thumbnail(url='https://i.pinimg.com/originals/59/50/f0/5950f0a238dae9016bcbc853feb9726d.gif')

    await ctx.channel.send(embed = EMBED)



@bot.command()
async def google(ctx, *,keyword : str):

    msg = f'https://www.google.com/search?q={keyword}'
    EMBED = discord.Embed(title='นี่ใช่สิ่งที่คุณกำลังมองหาหรือไม่',description=msg,color=0x42ff21)
    EMBED.set_thumbnail(url='https://i.pinimg.com/originals/59/50/f0/5950f0a238dae9016bcbc853feb9726d.gif')

    await ctx.channel.send(embed = EMBED)

bot.run(token)
