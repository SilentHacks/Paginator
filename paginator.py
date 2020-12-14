import asyncio
import discord
from lib.utils import build_queue


class Paginator:
    def __init__(self, ctx, entries: list, title, footer=None, queue_type=None, search=None, total_cards=0, embed=True):
        self.bot = ctx.bot
        self.ctx = ctx
        self.title = title  # Page title
        self.footer = footer  # Page footer
        self.entries = entries  # List where each element is a page in this embed
        self.embed = embed  # Whether the list is made up of embeds or not
        self.queue_type = queue_type  # Pagination type
        self.search = search  # Search filter applied on content of pages
        self.embed_color = 0xD5E5FF
        self.total_cards = total_cards  # Total number of cards from all pages

        # Sets the correct number for max_pages (10 cards make up a page)
        if search:
            self.max_pages = len(entries) - 1
        else:
            self.max_pages = total_cards // 10
            if total_cards % 10 != 0:
                self.max_pages += 1

        self.msg = ctx.message
        self.paginating = True  # Flag to signal to keep listening for reactions
        self.user_ = ctx.author
        self.channel = ctx.channel
        self.current = 0  # Current page
        self.execute = None  # Will be set to one of the function below to execute that func
        self.reactions = [('\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}', self.first_page),
                          ('\N{BLACK LEFT-POINTING TRIANGLE}', self.backward),
                          ('\N{BLACK RIGHT-POINTING TRIANGLE}', self.forward),
                          ('\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}', self.last_page),
                          ('\N{INPUT SYMBOL FOR NUMBERS}', self.selector)]

    async def setup(self):
        """Turns the list into a list of embeds, assigned to self.entries and sends the first page. Adds the reactions after and if a search filter has not been placed,
        does a database function to grab the rest of the page contents from the database"""
        if not self.embed:
            self.entries = await self.make_pages()

        try:
            self.msg = await self.channel.send(embed=self.entries[0])
        except (AttributeError, TypeError):
            self.msg = await self.channel.send(embed=self.entries)

        if self.total_cards <= 10:
            return

        await self.add_reactions()
        if not self.search:
            await self.rebuild_queue()

    async def add_reactions(self):
        """Adds the reactions to the embed"""
        for (r, _) in self.reactions:
            await self.msg.add_reaction(r)

    async def rebuild_queue(self):
        """Database function to re-grab the rest of the contents of the pages from the database"""
        self.entries, _ = build_queue(user_id=str(self.user_.id), queue_type=self.queue_type, search=self.search)
        self.entries = await self.make_pages()
        self.max_pages = len(self.entries) - 1

    async def alter(self, page: int):
        """Changes the page of the embed by changing it to another page from the list"""
        try:
            await self.msg.edit(embed=self.entries[page])
        except IndexError:
            await self.msg.edit(content=self.entries[page - 1])

    async def make_pages(self):
        """Converts a list of strings into a list of embeds with appropriate headers/footers/content"""
        embeds = []
        counter = 1
        if self.search:
            max_pages = self.max_pages + 1
        else:
            max_pages = self.max_pages

        if not self.entries:
            self.entries = ['']

        for page in self.entries:
            embed = discord.Embed(title=self.title, description=page, color=self.embed_color)
            if not self.footer:
                embed_footer = f"Page {counter} of {max_pages}"
            else:
                embed_footer = f"{self.footer}\nPage {counter} of {max_pages}"
            embed.set_footer(text=embed_footer)
            counter += 1
            embeds.append(embed)

        return embeds

    async def first_page(self):
        """Changes the page to the first page"""
        self.current = 0
        await self.alter(self.current)

    async def backward(self):
        """Changes the page one back (loops to the front)"""
        if self.current == 0:
            self.current = self.max_pages
        else:
            self.current -= 1
        await self.alter(self.current)

    async def forward(self):
        """Changes the page one forward (loops to the back)"""
        if self.current == self.max_pages:
            self.current = 0
        else:
            self.current += 1
        await self.alter(self.current)

    async def last_page(self):
        """Changes the page to the last page"""
        self.current = self.max_pages
        await self.alter(self.current)

    def selector_check(self, m):
        """Predicate for when the 'selection' emote is used to validate the page the user wants to turn to"""
        if m.author != self.user_:
            return False

        if m.channel.id != self.ctx.channel.id:
            return False

        if m == self.msg:
            return True

        try:
            if 1 <= int(m.content) <= self.max_pages + 1:
                return True
        except ValueError:
            return False
        return False

    async def selector(self):
        """Waits for the user to enter the page number that they want to skip to"""
        delete = await self.channel.send(f"Which page do you want to turn to? **1-{self.max_pages + 1}?**")
        try:
            number = int((await self.bot.wait_for('message', check=self.selector_check, timeout=60)).content)
        except asyncio.TimeoutError:
            return await self.ctx.send("You ran out of time.")
        else:
            self.current = number - 1
            await self.alter(self.current)
            await delete.delete()

    async def stop(self):
        """Stops the pagination"""
        self.paginating = False

    def reaction_check(self, reaction, user):
        """Predicate for checking the reaction on the page of the embed"""
        if user.id != self.user_.id:
            return False

        if reaction.message.id != self.msg.id:
            return False

        for (emoji, func) in self.reactions:
            if reaction.emoji == emoji:
                self.execute = func
                return True
        return False

    async def paginate(self):
        """Sets up the embed and listens with timeout for a reaction before executing that function"""
        await self.setup()  # Sets up the embed and pages
        while self.paginating:

            try:
                # Waits for the user to react on one of the emotes of the embed
                # TODO: After 1000 messages, this message is no longer and cache and reactions are not checked, leading to problems
                reaction, user = await self.bot.wait_for('reaction_add', check=self.reaction_check, timeout=60)
            except asyncio.TimeoutError:
                # Stops paginating if they have not reacted within one minute of their last reaction
                return await self.stop()

            # Attempts to remove the reaction they have placed (dependent on permissions)
            try:
                await self.msg.remove_reaction(reaction, user)
            except discord.HTTPException:
                pass

            # Executes the assigned func based on what the user reacted with on the embed
            await self.execute()
