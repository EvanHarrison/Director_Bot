import os
import asyncio
import discord
import requests
from dotenv import load_dotenv
import sqlite3
import io
import aiohttp

#Separate file in the same directory named .env is used to load in my API key and discord token
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
TMDB_KEY = os.getenv("TMDB_Key")



class Director(discord.Client):
    async def on_ready(self):

        print(f'{client.user} has connected to Discord!')

        #Connects to the sqlite3 database and initializes the tables if they are not already present
        conn = sqlite3.connect(f'REPLACE') #Replace this with the path to your database
        cur = conn.cursor()
        sql_query = """SELECT name FROM sqlite_master WHERE type='table';"""
        cur.execute(sql_query)

        if len(cur.fetchall()) < 4:
            cur.execute("""CREATE TABLE Movies (id INTEGER, title TEXT, RatingAvg FLOAT, genre_id INTEGER, TMDB_ID INTEGER, ReleaseDate TEXT, PRIMARY KEY (id))""")
            cur.execute("""CREATE TABLE Users (id INTEGER, USERNAME TEXT, PRIMARY KEY (id)) """)
            cur.execute("""CREATE TABLE UserReview (user_id INTEGER, movie_id INTEGER, rating FLOAT, PRIMARY KEY(user_id,movie_id)) """)
            cur.execute("""CREATE TABLE Genre (id INTEGER, description TEXT, PRIMARY KEY (id)) """)

            #Fills the genre table for reference later
            genres_url = "https://api.themoviedb.org/3/genre/movie/list?api_key="
            full_url = genres_url + TMDB_KEY
            genres = requests.get(full_url)
            genres_json = genres.json()
            for i in range(len(genres_json['genres'])):
                genre_id = genres_json['genres'][i]['id']
                genre_name = genres_json['genres'][i]['name']
                cur.execute("""INSERT INTO Genre (id,description) VALUES (?,?)""",(genre_id,genre_name,))
                conn.commit()


    async def on_message(self,message):

        #Inner function for when you want to get any movie/tv show name
        async def TMDB_get_info():
            await message.channel.send("What movie? ")
            movie_response =  await self.wait_for('message', timeout=30.0)
            movie_response = str(movie_response.content)            
            TMDB_url_base = "https://api.themoviedb.org/3/search/movie?query="
            movie_querey = movie_response.replace(" ","+")
            full_URL = TMDB_url_base + movie_querey + "&api_key=" + TMDB_KEY
            response = requests.get(full_URL)
            return response.json()

        #Inner function here to loop through the movies that you get from TMDB_get_info and send a multiple choice question out to choose the correct movie
        async def PickMovie(data):
            data_length = len(data['results'])
            options = ["A","B","C","D"]
            index = 0
            loop_value = "GO"
            while loop_value == "GO":

                #For when the movie search returns no movies
                if data_length == 0:
                    return await message.channel.send("No movies found. Check movie title and try again.")
                     

                title_dic = {}
                for i in options[0:3]:
                    if index >= data_length:
                        break
                    else:         
                        title_dic[i] = (data['results'][index]['title'], data['results'][index]['release_date'],data['results'][index]["id"],data['results'][index]['genre_ids'])
                        index += 1

                for i in title_dic:
                    await message.channel.send("%s: %s (%s)"%(i,title_dic[i][0],title_dic[i][1]))

                #This finds the index of the last movie entry in the dictionary "title_dic" so that the last letter of the multiple choice prompt is alway 1 after the last movie. e.g. A: movie, B: last movie, C: None of these are correct
                    
                last_key = list(title_dic)[-1]
                lastspot = options.index(last_key)
                last_letter = options[(lastspot + 1)]
     
                await message.channel.send("%s: None of these are correct."% (last_letter) )
    
                #Saves the answer to the multiple choice prompt
                selection_resp = await self.wait_for('message',timeout = 30)
                cap_selection = selection_resp.content.upper()

                #Checks to make sure it is not recording any messages that the bot sent as an answer to the multiple choice prompt
                if message.author.id != self.user.id:

                    if cap_selection not in options:
                        await message.channel.send("Respond with only the letter on the left. Try again.")
                        selection_resp = await self.wait_for('message',timeout = 30)
                        cap_selection = selection_resp.content.upper()

                #If the answer to the multiple choice messages is not the "None of these are correct" option then it returns information about the movie selected
                    if cap_selection != last_letter:
                        movie = title_dic[cap_selection][0]
                        TMDBID = title_dic[cap_selection][2]
                        movie_release = title_dic[cap_selection][1]
                        genre_list = title_dic[cap_selection][3]
                        loop_value = "STOP"

                        return movie,TMDBID,movie_release,genre_list
                
                #If you cycle through all of the movies from the search earlier then it sends a message to try again
                    elif (cap_selection == last_letter) and (index >= data_length):
                        return await message.channel.send("I cannot find your movie. Please check the movie title again.") 
                

        conn = sqlite3.connect(f'REPLACE') #Replace this with the path to your database
        cur = conn.cursor()

        if message.author.id == self.user.id:
            return
        
        #d!add is to add a movie that was watched to the sqlite3 database with the movie title/id, user id, and the user review of the movie
        if message.content.startswith("d!add"):
            try:            
                data = await TMDB_get_info()
                
                sel_movie = await PickMovie(data)
                movie = sel_movie[0]
                TMDBID = sel_movie[1]
                movie_release = sel_movie[2]  
                genre_list = sel_movie[3]

                #Checks if the movie is already in the database. If not then it is added
                cur.execute("""SELECT id FROM Movies WHERE TMDB_ID = (?)""",(TMDBID,))
                movie_exists = cur.fetchone()

                if movie_exists is None:
                    cur.execute("""INSERT INTO Movies (title,ReleaseDate,TMDB_ID)  VALUES (?,?,?)""",(movie,movie_release,TMDBID,genre_list))
                    conn.commit()

                await message.channel.send("How many people watched it?")

                num_watchers_response = await self.wait_for('message', timeout = 30.0)
                num_watcher = num_watchers_response.content
                num_watcher_int = int(num_watcher)

                await message.channel.send(f'How was it? (Out of 10)')

                for i in range(num_watcher_int):

                    rating_response = await (self.wait_for('message',timeout = 30.0))
                    rating = rating_response.content

                    usernames_SQL = cur.execute("""SELECT USERNAME from Users""")

                    usernames = [name[0] for name in cur.fetchall()] #list comprehension to get the first username from the sql query

                    cur.execute("""SELECT id FROM Users WHERE USERNAME = (?)""",(rating_response.author.name,))
                    userID = cur.fetchone()
                    
                #Checks to see if the user has made an entry before. If not then they are added to the database
                    if userID is None:   
                        cur.execute("""INSERT INTO Users (USERNAME) VALUES (?)""",(rating_response.author.name,))
                        conn.commit()
                        userID = rating_response.author.name
                    
                    
                    movieID_SQL = cur.execute("""SELECT id from Movies WHERE title = (?)""",(movie,))
                    movieID = movieID_SQL.fetchone()
                    
                #if the same user trys to add a review it replaces the previous rating with the new one
                    cur.execute("""SELECT user_id,movie_id FROM UserReview INNER JOIN Users ON UserReview.user_id = Users.id WHERE Users.USERNAME = (?) AND UserReview.movie_id = (?)""",(rating_response.author.name,movieID[0]))
                    seen_it_before = cur.fetchone()
                    if seen_it_before is None:
                        cur.execute("""INSERT INTO UserReview (user_id,movie_id,rating) values (?,?,?)""",(userID[0],movieID[0],rating,)) 
                        conn.commit()
                    else:
                        cur.execute("""UPDATE UserReview SET rating = (?) WHERE EXISTS (SELECT UserReview.movie_id,UserReview.user_id FROM UserReview INNER JOIN Users ON UserReview.user_id = Users.id WHERE Users.USERNAME = (?) AND UserReview.movie_id = (?) )""",(rating,rating_response.author.name,movieID[0]))
                        conn.commit()

                #Finally to update the average rating of a movie
                cur.execute("""SELECT avg(rating) FROM UserReview WHERE UserReview.movie_id = (?)""",(movieID[0],))
                AVG_rating = cur.fetchone()[0]
                cur.execute("""UPDATE Movies SET RatingAvg = (?)""",(AVG_rating,))
                conn.commit()


                return await message.channel.send(f"Your Review of %s has been added." % (movie))
            

            except asyncio.TimeoutError:
                return await message.channel.send(f'Allowed response time exceeded. Please start again.')
        
        #d!myinfo looks up the user based on who typed it and then returns how many movies they have watched and what their favorite movie is. 
        if message.content.startswith("d!myinfo"):
            
            cur.execute("""SELECT UserReview.movie_id, COUNT(*) from UserReview INNER JOIN Users ON UserReview.user_id = Users.id WHERE Users.USERNAME = (?)""",(message.author.name,)) #SQL to count how many movies have been entered
            movie_count = cur.fetchone()[0]
            
            cur.execute("""SELECT Movies.title, UserReview.Rating FROM UserReview INNER JOIN Users ON UserReview.user_id = Users.id INNER JOIN Movies On UserReview.movie_id = Movies.id WHERE Users.USERNAME = (?) ORDER BY UserReview.Rating DESC LIMIT 1""",(message.author.name,))
            fav_movie = cur.fetchone()
            fav_title = fav_movie[0]
            fav_rating = fav_movie[1]
            print(movie_count,fav_title,fav_rating)


            return await message.channel.send(f'You have watched %i movies! \nYour favorite was %s with a rating of %f' % (movie_count,fav_title,fav_rating))  
            

            #return await message.channel.send(f"%s, you have watched %i movies. \n Your favorite movie is %s with a rating of %f." % (message.content.author, movies_watched, favorite_movie, fav_rating)

        #d!getinfo is for looking up some basic information about a certain movie (Poster,Release,Genre,Overview,Rating)
        if message.content.startswith("d!getinfo"):
            data = await TMDB_get_info()
            select_movie = await PickMovie(data)
            movie = select_movie[0]
            single_json = [data["results"][val] for val in range(len(data['results'])) if data['results'][val]["title"] == movie] #list comprehension to get only the json entry that is for the movie you choose

            overview = single_json[0]['overview']
            release_date = select_movie[2]
            vote_average = single_json[0]['vote_average']
            genre = single_json[0]['genre_ids']

            genre_string = ""
            for i in genre:
                cur.execute("""SELECT description FROM Genre WHERE id = (?)""",(i,))
                genre_name = cur.fetchone()
                if genre[-1] == i:
                    genre_string = genre_string + genre_name[0]
                else:
                    genre_string = genre_string + genre_name[0] + ", "

        #Finds the poster path and converts it to a discord file to send to the channel
            base_url = "https://image.tmdb.org/t/p/"
            size_image = "w185"
            jpg_url = single_json[0]["poster_path"]
            url = base_url + size_image + jpg_url 

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return await message.channel.send('Could not download file...')
                    image_data = io.BytesIO(await resp.read())
                    await message.channel.send(file=discord.File(image_data, 'cool_image.png'))

            await message.channel.send("Released: %s\nGenre: %s\nOverview: %s\nRating: %i "% (release_date,genre_string,overview,vote_average))


intents = discord.Intents.default()
intents.message_content = True

client = Director(intents=intents)
client.run(TOKEN)