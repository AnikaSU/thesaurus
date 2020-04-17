import asyncio
import pickle
import timeit
import dill
import numpy as np

from thesaurus import fetch_list_of_words, Word

l = ['good','bad','apple','evil','man','kind','cup','orange','fine','worse','ok','yellow','mug','grass','green','women']
start = timeit.default_timer()
words_dict = asyncio.run(fetch_list_of_words(l))
stop = timeit.default_timer()
print(words_dict)
with open('l_words.pickle','wb') as f:
    dill.dump(words_dict,f)
print('Time: ', stop - start)

with open('l_words.pickle','rb') as f:
    thesauri = dill.load(f)
print(thesauri)