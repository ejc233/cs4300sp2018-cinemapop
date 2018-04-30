from . import *
from app.irsystem.models.helpers import *
from app.irsystem.models.helpers import NumpyEncoder as NumpyEncoder
import json
import math
import user_duration
import user_release
import boosting
import utils
import scipy.stats
import operator
from random import *
import datetime

movies_json = json.load(open('app/static/data/movies.json'))

# map each movie id to the movie's information
movie_dict = dict()
for movie in movies_json:
    movie_dict[movie['id']] = json.load(open('app/static/data/movies/' + movie['id'] + '.json'))
    dt = datetime.datetime.strptime(str(movie_dict[movie['id']]['release_date']), '%Y-%m-%d').strftime('%m-%d-%Y')
    movie_dict[movie['id']]['release_date'] = dt
reverse_dict = {y['title'].lower():x for x,y in movie_dict.iteritems()}

max_tmdb_count = 16891.0
max_imdb_count = 1938672.0
max_meta_count = 56.0

# get list of years
year_list = range(1900, 2019)

@irsystem.route('/', methods=['GET'])
def search():
    data = []

    # user inputs
    similar = request.args.get('similar')
    genres = request.args.get('genres')
    castCrew = request.args.get('castCrew')
    keywords = request.args.get('keywords')
    duration = request.args.get('duration')
    release_start = request.args.get('release_start')
    release_end = request.args.get('release_end')
    ratings = request.args.get('ratings')
    languages = request.args.get('languages')
    acclaim = request.args.get('acclaim')
    popularity = request.args.get('popularity')

    if not acclaim and not popularity:
        data = []
    else:
        data = []
        filtered_movie_dict = dict(movie_dict)
        query_dict = dict()

        ########### QUERY DICT GENERATION ###########
        if similar:
            selected_movies = parse_lst_str(similar)
        if genres:
            selected_genres = parse_lst_str(genres)
            query_dict['genres'] = selected_genres
        if castCrew:
            selected_crew = parse_lst_str(castCrew)
            query_dict['castCrew'] = selected_crew
        if keywords:
            selected_keywords = parse_lst_str(keywords)
            query_dict['keywords'] = keywords
        if duration:
            duration_val = user_duration.parse(duration)
            duration_val = duration_val[0] if len(duration_val) == 1 else (duration_val[0] + duration_val[1])/2
            query_dict['runtime'] = duration_val
        if ratings:
            selected_ratings = parse_lst_str(ratings)
        if languages:
            selected_languages = parse_lst_str(languages)


        ########### FILTERING OF DICTIONARIES ###########
        # updates dicts with hard filters
        if duration:
            filtered_movie_dict = user_duration.main(filtered_movie_dict,duration,1)
            duration_score_dict = boosting.gaussian_score_duration(filtered_movie_dict,query_dict['runtime'],1,0)
        if release_start or release_end:
            filtered_movie_dict = user_release.main(filtered_movie_dict,[release_start, release_end])
        if ratings:
            filtered_movie_dict = utils.filter_ratings(filtered_movie_dict, selected_ratings)
        if languages:
            filtered_movie_dict = utils.filter_languages(filtered_movie_dict, selected_languages)
        if acclaim == 'yes':
            acclaim_score_dict = utils.half_gaussian_acclaim(filtered_movie_dict, 1, 0)

        ########### BOOST THE "QUERY MOVIE" WITH THE SIMILAR MOVIES ###########
        if similar:
            similar_tup_lst = []
            for similar_mov in selected_movies:
                similar_id = reverse_dict[similar_mov]
                similar_genres = movie_dict[similar_id]['genres']
                sim_cast = [member['name'] for member in movie_dict[similar_id]['cast']]
                sim_crew = [member['name'] for member in movie_dict[similar_id]['crew']]
                similar_castCrew = sim_cast + sim_crew
                sim_release_year = user_release.parse_single(movie_dict[similar_id]['release_date'])
                similar_tup_lst.append((similar_id,similar_genres,similar_castCrew,sim_release_year))
            filtered_movie_dict = utils.filter_similar(filtered_movie_dict,selected_movies)
            ranked_sim_lst = [utils.get_similar_ranking(tup,filtered_movie_dict) for tup in similar_tup_lst]

        ########### VECTORIZE MOVIES GIVEN QUERY ###########
        movie_feature_lst,movie_id_lookup = [],{}
        for index,movie in enumerate(filtered_movie_dict):
            features_lst = []
            filtered_movie_dict[movie]['scores'] = dict()

            if similar:
                cumulative_score = 0.0
                for sim_movie in selected_movies:
                    sim_id = reverse_dict[sim_movie]
                    genres_score = utils.get_set_overlap(movie_dict[sim_id]['genres'],filtered_movie_dict[movie]['genres'])
                    sim_cast = [member['name'] for member in movie_dict[sim_id]['cast']]
                    sim_crew = [member['name'] for member in movie_dict[sim_id]['crew']]
                    cast = [member['name'] for member in filtered_movie_dict[movie]['cast']]
                    crew = [member['name'] for member in filtered_movie_dict[movie]['crew']]
                    cast_score = utils.get_set_overlap(sim_cast + sim_crew, cast + crew)
                    keywords_score = utils.get_set_overlap(movie_dict[sim_id]['keywords'],filtered_movie_dict[movie]['keywords'])
                    cumulative_score += (2.0 * genres_score + cast_score + keywords_score) / 4.0
                filtered_movie_dict[movie]['scores']['similar'] = round(cumulative_score / len(selected_movies), 2)

            # list of genres for movie m -> jaccard sim with query
            if genres:
                genres_score = utils.get_set_overlap(query_dict['genres'],filtered_movie_dict[movie]['genres'])
                filtered_movie_dict[movie]['scores']['genres'] = round(genres_score, 2)
                features_lst.append(genres_score)

            # list of cast and crew for movie m -> jaccard sim with the query
            if castCrew:
                cast = [member['name'] for member in filtered_movie_dict[movie]['cast']]
                crew = [member['name'] for member in filtered_movie_dict[movie]['crew']]
                castCrew_score = utils.get_set_overlap(query_dict['castCrew'], cast + crew)
                filtered_movie_dict[movie]['scores']['cast'] = round(castCrew_score, 2)
                features_lst.append(castCrew_score)

            # keywords from query -> jaccard sim with the movie m synopsis
            if keywords:
                keywords_score = utils.get_set_overlap(selected_keywords, filtered_movie_dict[movie]['keywords'])
                filtered_movie_dict[movie]['scores']['keywords'] = round(keywords_score, 2)
                features_lst.append(keywords_score)

            # duration & release date from movie m -> probabilistic gaussian fit around the mean
            if duration and len(user_duration.parse(duration)) == 1:
                duration_score = duration_score_dict[movie]
                filtered_movie_dict[movie]['scores']['duration'] = round(duration_score, 2)
                features_lst.append(duration_score)

            if duration and len(user_duration.parse(duration)) == 2:
                filtered_movie_dict[movie]['scores']['duration'] = 1.0

            if release_start or release_end:
                filtered_movie_dict[movie]['scores']['release'] = 1.0

            # acclaim -> value between 0 and 1
            if acclaim == "yes":
                acclaim_score = acclaim_score_dict[movie]
                filtered_movie_dict[movie]['scores']['acclaim'] = round(acclaim_score, 2)
                features_lst.append(acclaim_score)

            # popularity -> value between 0 and 1
            if popularity == "yes":
                popularity_score = utils.calc_popularity(filtered_movie_dict,movie,max_tmdb_count,max_imdb_count,max_meta_count)
                filtered_movie_dict[movie]['scores']['popularity'] = round(popularity_score, 2)
                features_lst.append(popularity_score)

            if ratings:
                filtered_movie_dict[movie]['scores']['ratings'] = 1.0

            if languages:
                filtered_movie_dict[movie]['scores']['languages'] = 1.0

            movie_feature_lst.append(features_lst)
            movie_id_lookup[index] = movie

        movie_matrix = np.zeros((len(movie_feature_lst),len(movie_feature_lst[0])))
        for i in range(len(movie_feature_lst)):
            for k in range(len(movie_feature_lst[i])):
                movie_matrix[i][k] = movie_feature_lst[i][k]

        ########### RUN KNN ON VECTORS, RETURN TOP MATCHES ###########
        n,d = movie_matrix.shape
        query = np.ones(d)
        dists = np.linalg.norm(movie_matrix - query,axis=1,ord=2)
        ranked_lst = np.argsort(dists)
        sorted_movie_list = [movie_id_lookup[movie_id] for movie_id in ranked_lst]


        ########### CONSILIDATE WITH THE SIMILAR MOVIE LIST ###########
        if similar:
            scored_movie_dict = {}

            # if similar movies is the only user input which is filled out, don't consider the sorted_movie_list
            if genres or castCrew or keywords:
                for index,movie in enumerate(sorted_movie_list):
                    scored_movie_dict[movie] = index
            for lst in ranked_sim_lst:
                for index,movie in enumerate(lst):
                    if movie not in scored_movie_dict:
                        scored_movie_dict[movie] = 0
                    scored_movie_dict[movie] += index

            # compute the percentage that it's a similar movie vs. user input
            # sim_percentage_dict = percentage influence the similar movies played in this calculation
            # sim_percentage_dict = {}
            # for index,movie in enumerate(sorted_movie_dict):
            #     if genres or castCrew or keywords:
            #         sim_percentage_dict[movie] = 1 - ((scored_movie_dict[movie] - index)/scored_movie_dict[movie])
            #     else:
            #         sim_percentage_dict[movie] = 1

            sorted_movie_dict = sorted(scored_movie_dict.items(), key=operator.itemgetter(1))
            sorted_movie_list = [k for k,v in sorted_movie_dict]

        ########### TRANSFORM THE SORTED LIST INTO FRONT-END FORM ###########
        for movie_id in sorted_movie_list[:24]:
            data.append(filtered_movie_dict[movie_id])
        data = [data[i:i + 4] for i in xrange(0, len(data), 4)]

    return render_template('search.html',
        old_similar = xstr(similar),
        old_genres = xstr(genres),
        old_castCrew = xstr(castCrew),
        old_keywords = xstr(keywords),
        old_duration = xstr(duration),
        old_release_start = xstr(release_start),
        old_release_end = xstr(release_end),
        old_ratings = xstr(ratings),
        old_languages = xstr(languages),
        old_acclaim = xstr(acclaim),
        old_popularity = xstr(popularity),
        data = data,
        year_list = year_list)

def parse_lst_str(lst_str):
    parsed = []
    if lst_str:
        lst_str = lst_str.encode('ascii', 'ignore')
        if ';' in lst_str:
            parsed = lst_str.split(";")
        else:
            parsed = [lst_str]
        for ind in range(0, len(parsed)):
            parsed[ind] = parsed[ind].lower().strip()
    return parsed

# set string to empty string if string is None type
def xstr(s):
    return '' if s is None else str(s)
