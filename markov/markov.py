from redbot.core.utils.chat_formatting import *
from redbot.core import Config, checks, commands
import discord
import random
import asyncio


class Markov(commands.Cog):
    """ Generate text based on what your members say per channel"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=5989735216541313, force_registration=True)

        default_guild = {"model": {}, "prefixes": [], "max_len": 200}
        self.config.register_guild(**default_guild)
        self.cache = {}
        self.init_task = asyncio.create_task(self.init())

    def cog_unload(self):
        self.init_task.cancel()
        # save all the models before full unload/shutdown
        for guild in self.bot.guilds:
            asyncio.create_task(self.config.guild(guild).model.set(self.cache[guild.id]["model"]))

    async def init(self):
        await self.bot.wait_until_ready()
        # caches all the models, uses more ram but bot
        # slows down once file gets big otherwise
        for guild in self.bot.guilds:
            self.cache[guild.id] = await self.config.guild(guild).all()

        while True:  # save model every 5 minutes
            await asyncio.sleep(300)
            for guild in self.bot.guilds:
                await self.config.guild(guild).model.set(self.cache[guild.id]["model"])

    @commands.group()
    @checks.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def markovset(self, ctx):
        """ Manage Markov Settings """
        pass

    @markovset.command(name="clear")
    async def markovset_clear(self, ctx, *, channel: discord.TextChannel):
        """ Clear data for a specific channel """
        async with self.config.guild(ctx.guild).model() as model:
            del self.cache[ctx.guild.id]["model"][str(channel.id)]
            try:  # possible that channel is cached but not saved yet
                del model[str(channel.id)]
            except:
                pass
        await ctx.tick()

    @markovset.command(name="prefix")
    async def markovset_prefixes(self, ctx, *, prefixes: str = None):
        """Set prefixes for bots in your server
        This is so markov won't log bot commands.
        """
        if not prefixes:
            current = self.cache[ctx.guild.id]["prefixes"]
            curr = [f"`{p}`" for p in current]
            if not current:
                await ctx.send("No prefixes set, setting this bot's prefix.")
                await self.config.guild(ctx.guild).prefixes.set([ctx.clean_prefix])
                self.cache[ctx.guild.id]["prefixes"] = [ctx.clean_prefix]
                return

            await ctx.send("Current Prefixes: " + humanize_list(curr))
            return

        prefixes = [p for p in prefixes.split(" ") if p != ""]
        self.cache[ctx.guild.id]["prefixes"] = prefixes
        await self.config.guild(ctx.guild).prefixes.set(prefixes)
        prefixes = [f"`{p}`" for p in prefixes]
        await ctx.send("Prefixes set to: " + humanize_list(prefixes))

    @markovset.command(name="len")
    async def markovset_length(self, ctx, length: int = None):
        """
        Set max characters of generated text.

        Max size is 2800.
        """
        if not length:
            curr = self.cache[ctx.guild.id]["max_len"]
            await ctx.send(f"Current max length of generated text is `{curr}` characters.")
            return

        if length > 2800:
            await ctx.send(error("Max length is 2800."))
            return

        self.cache[ctx.guild.id]["max_len"] = length
        await self.config.guild(ctx.guild).max_len.set(length)
        await ctx.tick()

    @commands.command(name="markov")
    @commands.guild_only()
    @commands.cooldown(rate=1, per=10, type=commands.BucketType.user)
    @checks.bot_has_permissions(embed_links=True)
    async def markov(self, ctx, *, starting_text: str = None):
        """Generate text using markov chains!

        Text generated is based on what users say in the current channel
        """
        model = self.cache[ctx.guild.id]["model"]
        try:
            model = model[str(ctx.channel.id)]
        except KeyError:
            await ctx.send(error("This channel has no data, try talking in it for a bit first!"))
            return

        starting_text = starting_text.split(" ") if starting_text else None
        last_word = starting_text[-1] if starting_text else None

        if not starting_text:
            markov_text = [random.choice(list(model.keys()))]
        elif last_word not in model or not model[last_word]:
            markov_text = starting_text + [random.choice(list(model.keys()))]
        else:
            markov_text = starting_text + [random.choice(model[last_word])]

        max_len = self.cache[ctx.guild.id]["max_len"]

        tries = 0
        max_tries = 20
        num_chars = len(" ".join(markov_text))
        while num_chars < max_len and tries < max_tries:
            if "?" in markov_text[-1]:
                break
            if "\r" in markov_text[-1]:
                break
            if "." in markov_text[-1]:
                break
            if "!" in markov_text[-1]:
                break

            # make sure word is in the model and there is data for the word
            if markov_text[-1] in model and model[markov_text[-1]]:
                choice = random.choice(model[markov_text[-1]])
                num_chars += len(choice)
                markov_text.append(choice)
            else:
                choice = random.choice(list(model.keys()))
                num_chars += len(choice)
                markov_text.append(choice)
                tries += 1

        markov_text = " ".join(markov_text)
        if num_chars > max_len:
            markov_text = markov_text[:max_len]
        member = ctx.author
        embed = discord.Embed(title="Generated Text", description=markov_text, colour=member.colour)

        if member.avatar:
            avatar = member.avatar_url_as(static_format="png")
            embed.set_thumbnail(url=avatar)

        embed.set_footer(text=f"Generated by {member.display_name}")
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.all())

    # Listener
    @commands.Cog.listener()
    async def on_message(self, message):
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        # updates model
        content = message.content
        guild = message.guild
        if not content or not message.guild or message.author == message.guild.me:
            return

        # check if this is a bot message
        prefixes = self.cache[guild.id]["prefixes"]
        for prefix in prefixes:
            if prefix == content[: len(prefix)]:
                return

        content = content.split(" ")
        model = self.cache[guild.id]["model"]

        try:
            model[str(message.channel.id)]
        except KeyError:
            model[str(message.channel.id)] = {}

        for i in range(len(content) - 1):
            if content[i] not in model[str(message.channel.id)]:
                model[str(message.channel.id)][content[i]] = list()

            model[str(message.channel.id)][content[i]].append(content[i + 1])

        self.cache[guild.id]["model"] = model
