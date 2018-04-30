import scipy.stats

def parse(inp):
	if not inp[0]:
		inp[0] = '1900'
	if not inp[1]:
		inp[1] = '2018'
	if inp[0] < inp[1]:
		lst = [int(entry[:4].strip()) for entry in inp]
		return lst
	else:
		lst = [int(entry[:4].strip()) for entry in inp]
		lst.reverse()
		return lst
	return [int(inp[0][:4].strip())]

def parse_single(inp):
	return int(inp[-4:].strip())

def filter_hard(movie_dict,low_bound, high_bound,):
	rtn_movie = {}
	for movie in movie_dict:
		if int(movie_dict[movie]['release_date'][-4:]) >= low_bound and int(movie_dict[movie]['release_date'][-4:]) <= high_bound:
			rtn_movie[movie] = movie_dict[movie]
	return rtn_movie

def gaussian_release_score(movie_dict,mean,high_val,low_val):
    score_dict = {}
    movie_to_weight = {}

    dist = scipy.stats.norm(mean,16)
    for movie in movie_dict:
        movie_to_weight[movie] = dist.pdf(int(movie_dict[movie]['release_date'][-4:]))

    # movie -> weight value between 0 and 1
    max_val,min_val = max(movie_to_weight.values()), min(movie_to_weight.values())
    movie_to_weight = {k:((v - min_val)/(max_val - min_val)) for k,v in movie_to_weight.iteritems()}

    # movie -> weight value between high and low
    for movie in movie_to_weight:
        score_dict[movie] = (movie_to_weight[movie]*(high_val + low_val) - low_val)
    return score_dict


def main(movie_dict, inp):
	vals = parse(inp)
	if len(vals) == 2:
		return filter_hard(movie_dict,vals[0],vals[1])
	return filter_hard(movie_dict,vals[0],vals[0])