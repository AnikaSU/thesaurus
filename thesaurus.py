"""
Thesaurus-API
~~~~~~~~~~~~~

An api for thesaurus.com. See the README for instructions.

A pythonic poem authored by Robert.
Inspiration and help from others (see credits).

If there's anything in here you don't understand or want me to change, just
make an issue or send me an email at robert <at> robertism <dot> com. Thanks :)
"""
import asyncio
import sys
from collections import namedtuple
import json

# import requests
import aiohttp
from bs4 import BeautifulSoup

# how we will represent an individual synonym/antonym
# put it here in order to pickle it in multiprocessing
Entry = namedtuple('Entry', ['word', 'relevance', 'length',
                             'complexity', 'form'])


# ===========================   GLOBAL CONSTANTS   =============================
ALL = 'all'

## form=
FORM_INFORMAL = 'informal'
FORM_COMMON =   'common'

# TODO: also include nltk pos_tagger constants
## partOfSpeech=
POS_ADJECTIVE, POS_ADJ =        'adj', 'adj'
POS_ADVERB, POS_ADV =           'adv', 'adv'
POS_CONTRADICTION, POS_CONT =   'contraction', 'contraction'
POS_CONJUNCTION, POS_CONJ =     'conj', 'conj'
POS_DETERMINER, POS_DET =       'determiner', 'determiner'
POS_INTERJECTION, POS_INTERJ =  'interj', 'interj'
POS_NOUN =                      'noun'
POS_PREFIX =                    'prefix'
POS_PREPOSITION, POS_PREP =     'prep', 'prep'
POS_PRONOUN, POS_PRON =         'pron', 'pron'
POS_VERB =                      'verb'
POS_ABBREVIATION, POS_ABB =     'abb', 'abb'
POS_PHRASE =                    'phrase'
POS_ARTICLE =                   'article'
# =========================   END GLOBAL CONSTANTS   ===========================

import logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s:%(name)s: %(message)s",
    level=logging.DEBUG,
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("thesauri")
logging.getLogger("chardet.charsetprober").disabled = True

def btw(inputString, lh, rh):
    """Extract a string between two other strings."""
    return inputString.split(lh, 1)[1].split(rh, 1)[0]

async def fetch_list_of_words(words):
    words_dict = {}
    tasks = []
    async with aiohttp.ClientSession() as session:

        # FIXME: multiprocessing seems can not speed up, test this in future
        # with concurrent.futures.ProcessPoolExecutor() as executor:
        #     for word in words:
        #         words_dict[word] = Word(word)
        #         tasks.append(words_dict[word].fetchWordData(session,executor))
        #     await asyncio.gather(*tasks)

        for word in words:
            words_dict[word] = Word(word)
            tasks.append(words_dict[word].fetchWordData(session))
        await asyncio.gather(*tasks)
    return words_dict

class Word(object):
    def __init__(self, inputWord):
        """Downloads and stores the data thesaurus.com has for a given word.

        Parameters
        ----------
        inputWord : str
            The word you wish to search for on thesaurus.com
        """
        # in case you want to visit it later
        self.word = inputWord
        self.re_grab = False
        self.url = self.formatWordUrl()

    def formatWordUrl(self):
        """Format our word in the url. I could've used urllib's quote thing, but
        this is more efficient I think. Let me know if there's a word it doesn't
        work for and I'll change it.
        """
        url = 'https://www.thesaurus.com/browse/'
        url = url + self.word.strip().lower().replace(' ', '%20')
        return url

    def parse_html(self, html, r_url):
        soup = BeautifulSoup(html, 'html.parser')

        # Traverse the javascript to find where they embedded our data. It keeps
        #   changing index. It used to be 12, now it's 15. Yay ads and tracking!
        data = soup.select('script')
        for d in reversed(data):
            if d.string[0:20] == 'window.INITIAL_STATE':
                data = d.string[23:-1] # remove 'window.INITIAL_STATE = ' and ';'
                #clean up disallowed undefined values in json:
                data = data.replace("undefined", "null")
                data = json.loads(data)
                break

        # Disambiguation. They believe we've misspelled it, and they're providing us
        #   with potentially correct spellings. Only bother printing the first one.
        if '/misspelling' in r_url:
            # TODO: Should we include a way to retrieve this data?
            otherWords = data.get('searchData', {}).get('spellSuggestionsData', [])
            if not otherWords:
                logger.error(
                    "No thesaurus results for word: %s. Did you possibly misspell it?",
                    self.word
                )
                return
                # raise MisspellingError(self.word, '')
            else:
                logger.error(
                    "No thesaurus results for word: %s. Did you mean %s?",
                    self.word,
                    otherWords[0].get('term')
                )
                return
                # raise MisspellingError(self.word, otherWords[0].get('term'))

        defns = []  # where we shall store data for each definition tab

        ## Utility functions to process attributes for our entries.
        # a syn/ant's relevance is marked 1-3, where 10 -> 1, 100 -> 3.
        calc_relevance = lambda x: [None, 10, 50, 100].index(x)
        calc_length = lambda x: 1 if x < 8 else 2 if x < 11 else 3
        calc_form = lambda x: 'informal' if x is True else 'common'

        # iterate through each definition tab, extracting the data for the section
        for defn in data['searchData']['tunaApiData']['posTabs']:
            # this dict shall store the relevant data we found under the current def
            curr_def = {
                'partOfSpeech': defn.get('pos'),
                'meaning': defn.get('definition'),
                'isVulgar': bool(int(defn.get('isVulgar'))),
                'syn': [],
                'ant': []
            }

            """
            the synonym and antonym data will each be stored as lists of tuples.
              Each item in the tuple corresponds to a certain attribute of the
              given syn/ant entry, and is used to filter out specific results when
              Word.synonym() or Word.antonym() is called.
            """

            ### NOTE, TODO ###
            """
            Currently, complexity is set to level == 0 as I hope it will return.
              Originally, it was 1-3. In thesaurus.com's newest update, they removed
              this complexity data, and made all other data difficult to locate.
              I can't imagine them deleting this data... we shall see.
            """

            for syn in defn.get('synonyms', []):
                # tuple key is (word, relevance, length, complexity, form, isVulgar)
                e = Entry(
                    word=syn['term'],
                    relevance=calc_relevance(abs(int(syn['similarity']))),
                    length=calc_length(len(syn['term'])),
                    complexity=0,
                    form=calc_form(bool(int(syn['isInformal'])))
                    # isVulgar=bool(syn['isVulgar']) # *Nested* key is useless.
                )

                curr_def['syn'].append(e)

            for ant in defn.get('antonyms', []):
                # tuple key is (word, relevance, length, complexity, form, isVulgar)
                e = Entry(
                    word=ant['term'],
                    relevance=calc_relevance(abs(int(ant['similarity']))),
                    length=calc_length(len(ant['term'])),
                    complexity=0,
                    form=calc_form(bool(int(ant['isInformal'])))
                    # isVulgar=bool(ant['isVulgar']) # *Nested* key is useless.
                )

                curr_def['ant'].append(e)

            defns.append(curr_def)

        # add origin and examples to the last element so we can .pop() it out later
        otherData = data['searchData']['tunaApiData']
        examples = [x['sentence'] for x in otherData['exampleSentences']]
        etymology = otherData.get('etymology',[])

        if len(etymology) > 0:
            origin = BeautifulSoup(etymology[0]['content'], "html.parser").text
            ## Uncomment this if you actually care about getting the ENTIRE
            ##   origin box. I don't think you do, though.
            # origin = reduce(lambda x,y: x+y, map(
            #     lambda z: BeautifulSoup(z['content'], "html.parser").text
            # ))
        else:
            origin = ''

        defns.append({
            'examples': examples,
            'origin': origin
        })
        return defns

    async def fetch_html(self,url,session):
        resp = await session.request(method="GET", url=url)
        # resp.raise_for_status()
        logger.info("Got response [%s] for URL: %s", resp.status, url)
        html = await resp.text()
        return html,resp

    async def fetchWordData(self,session):
        """Downloads the data thesaurus.com has for our word.

        Parameters
        ----------
        inputWord : str
            The word you are searching for on thesaurus.com

        Returns
        -------
        list of dict
            A list of n+1 dictionaries, where n is the number of definitions for the
            word, and the last dictionary holds information on word origin and
            example sentences.

            Each definition dict is of the form:
                {
                    'meaning' : str,
                    'partOfSpeech' : str,
                    'isVulgar' : bool,
                    'syn' : [Entry(
                                    word=str,
                                    relevance=int,
                                    length=int,
                                    complexity=int,
                                    form=str
                            )],
                    'ant' : [... same as 'syn' ...]
                }
            where `Entry` is a namedtuple.
        """

        url = self.formatWordUrl()

        # Try to download the page source, else throw an error saying we couldn't
        #   connect to the website.
        try:
            html,r = await self.fetch_html(url,session)
        except (
            aiohttp.ClientError,
            aiohttp.http_exceptions.HttpProcessingError,
        ) as e:
            logger.error(
                "aiohttp exception for %s [%s]: %s",
                url,
                getattr(e, "status", None),
                getattr(e, "message", None),
            )
            return
        except Exception as e:

            # FIXME: show e information in logger
            # TODO: add another function to recapture the uncaputured words
            logger.error(
                "Error connecting to thesaurus.com :\n{0}\n".format(e)
            )
            self.re_grab = True
            return
            # raise ThesaurusRequestError(e)

        # The site didn't have this word in their collection.
        if '/noresult' in str(r.url):
            logger.error(
                "No thesaurus results for word: %s",
                self.word
            )
            return
            # raise WordNotFoundError(self.word)

        # FIXME: multiprocessing seems can not speed up, test this in future
        # loop = asyncio.get_running_loop()
        # with concurrent.futures.ProcessPoolExecutor() as executor:
        #     defns = await loop.run_in_executor(
        #             executor, self.parse_html,html, str(r.url))

        if html == '404 Not Found':
            logger.error(
                "404 Not Found for word: %s",
                self.word
            )
            return

        defns = self.parse_html(html,str(r.url))
        if defns:
            self.data = defns
            self.extra = self.data.pop()

        # return defns

    def __len__(self):
        # returns the number of definitions the word has
        return len(self.data)

    ### FUNCTIONS TO HELP ORGANIZE DATA WITHIN THE CLASS ###
    def _filter(self, mode, defnNum='all', **filters):
        """Filter out our self.data to reflect only words with certain
        attributes specified by the user. Ex: return informal synonyms that are
        relevant and have many characters.

        NOTE:
        COMPLEXITY filter is STILL BROKEN thanks to the site's update. It will
        simply be ignored for the time being.

        Parameters
        ----------
        mode : {'syn', 'ant'}
            Filters through the synonyms if 'syn', or antonyms if 'ant'.
        defnNum : int or 'all', optional
            The word definition we are filtering data from (index of self.data).
            Thus, as it is an index, it must be >= 0. If 'all' is specified,
            however, it will filter through all definitions. This is the default

        NOTE:
        The following filters are capable of being specified as explicit values,
        or lists of acceptable values. Ex: relevance=1 or relevance=[1,2].

        relevance : {1, 2, 3} or list, optional
            1 least relevant - 'enfeebled'
            2 
            3 most relevant  - 'elderly'
        partOfSpeech : { POS_* } or list, optional
            The following possible values are also defined as constants at the
            beginning of the file. You can call them as: POS_ADVERB or POS_ADV.
            The complete list is as follows:
                adjective: 'adj'
                adverb: 'adv'
                contraction: 'contraction'
                conjunction: 'conj'
                determiner: 'determiner'
                interjection: 'interj'
                noun: 'noun'
                prefix: 'prefix'
                preposition: 'prep'
                pronoun: 'pron'
                verb: 'verb'
                abbreviation: 'abb'
                phrase: 'phrase'
                article: 'article'
        length : {1, 2, 3} or list, optional
            1 shortest - aged
            2
            3 longest - experienced
        complexity : {1, 2, 3} or list, optional
            Reminder that this is CURRENTLY BROKEN. It will default to `None`, 
            no matter what values you choose.
            1 least complex
            2
            3 most complex
        form : {'informal', 'common'} or list, optional
            Similar to the partOfSpeech options, these values are also defined
            as constants: FORM_INFORMAL and FORM_COMMON.

            Before thesaurus.com changed their code, it used to be that the
            majority of words were neither informal nor common. Thus, it wasn't
            the case that common inferred not-informal. Now, however, all words
            are either informal or common.
        isVulgar : bool, optional
            Similar to partOfSpeech, if `True`, will blank out non-vulgar
            definition entries. If `False`, will filter out vulgar definitions.
            Think of it as having only two different POS's to select from.

        Returns
        -------
        list of list of str OR list of str
            If defnNum is set to 'all', it will filter over all definitions, and
            will return a list of list of str, where each nested list is a
            single definition.
            If defnNum is set to an integer, it will return a list of str, where
            the str's are the filtered words for that single definition.
        """

        def compare_entries(e1, e2):
            if isinstance(e2, list):
                if None in e2:
                    return True
                else:
                    return e1 in e2
            else:
                if None in {e1, e2}:
                    return True
                else:
                    return e1 == e2

        Filters = namedtuple('Filters', [
            'relevance',
            'partOfSpeech',
            'length',
            'complexity', # currently unavailable
            'form',
            'isVulgar'
        ])

        filters = filters.get('filters', {})
        for key, val in filters.items():
            # make all filters in list format, so 1 becomes [1]. This makes
            #   checking equality between entries and filters easier.
            if not isinstance(val, list):
                filters[key] = [val]
        
        # We can't change a namedtuple's values after creating it. We have to
        #   make sure it matches the user's filter value before we set it.
        _tempForm = filters.get('form')
        if _tempForm: # make sure it's not NoneType first.
            for i, _form in enumerate(_tempForm):
                if 'informal' in _form.lower():
                    _tempForm[i] = 'informal'
                elif 'common' in _form.lower():
                    _tempForm[i] = 'common'
                else:
                    # reset form to be None, thus ignoring the improper option
                    print('Please select `informal` or `common` for `form=` filter.')
                    print('Defaulting to select both.')
                    _tempForm = None
                    break

        fs = Filters(
            relevance=      filters.get('relevance'),
            partOfSpeech=   filters.get('partOfSpeech', filters.get('pos')),
            length=         filters.get('length'),
            complexity=     None, # not currently implemented.
            form=           _tempForm,
            isVulgar=       filters.get('isVulgar')
        )

        if defnNum == 'all':
            # examines all definition tabs for a word
            startRange, endRange = 0, len(self.data)
        else:
            # examines only the tab index specified (starting at 0)
            startRange, endRange = defnNum, defnNum+1
        
        filtered_data = []  # data we are going to return

        for defn in self.data[startRange:endRange]:
            # current defn tab is not of the pos we require. continue.
            if not compare_entries(defn['partOfSpeech'], fs.partOfSpeech):
                filtered_data.append([])
                continue
            
            # current defn tab is not of the vulgarity we require. continue.
            if not compare_entries(defn['isVulgar'], fs.isVulgar):
                filtered_data.append([])
                continue
            
            # holds all the relevant entries for this defn.
            cur_data = []

            for entry in defn.get(mode):
                if (
                    compare_entries(entry.relevance, fs.relevance) and
                    compare_entries(entry.length, fs.length) and
                    compare_entries(entry.form, fs.form)
                ):
                    cur_data.append(entry.word)
            
            # if we only care about a single definition, just return a 1d list.
            if defnNum != 'all':
                return cur_data

            filtered_data.append(cur_data)

        return filtered_data

    ### FUNCTIONS TO RETURN DATA YOU WANT ###
    """Each of the following functions allow you to filter the output
    accordingly: relevance, partOfSpeech, length, complexity, form.
    """
    def synonyms(self, defnNum=0, allowEmpty=True, **filters):
        """Return synonyms for specific definitions, filtered to only include
        words with specified attribute values.
        
        PLEASE see _filter()'s docstring or the README for more information on
        filtering.

        Parameters
        ----------
        defnNum : int or 'all', optional
            The word definition we are returning data from (index of self.data).
            Thus, as it is an index, it must be >= 0. If 'all' is specified,
            however, it will filter through all definitions. 0 is the default.
        allowEmpty : bool, optional
            Filters the output to only include defns (represented as lists) that
            are not empty after being filtered. Useful if you are trying to only
            see definitions of a certain part of speech. This way, you can
            enumerate over the returned values without having to worry if you're
            enumerating over an empty value.

        Returns
        -------
        list of list of str OR list of str
            If defnNum is set to 'all', it will include data from all
            definitions, returning a list of list of str, where each nested list
            is a single definition.
            If defnNum is set to an integer, it will return a list of str, where
            the str's are the filtered words for that single definition.
        """

        data = self._filter(mode='syn', defnNum=defnNum, filters=filters)

        # the word does not exist. return empty.
        if not data:
            return []
        
        if allowEmpty:
            return data
        else:
            return [d for d in data if len(d) > 0]

    def antonyms(self, defnNum=0, allowEmpty=True, **filters):
        """Return antonyms for specific definitions, filtered to only include
        words with specified attribute values.
        
        PLEASE see _filter()'s docstring or the README for more information on
        filtering.

        Parameters
        ----------
        defnNum : int or 'all', optional
            The word definition we are returning data from (index of self.data).
            Thus, as it is an index, it must be >= 0. If 'all' is specified,
            however, it will filter through all definitions. 0 is the default.
        allowEmpty : bool, optional
            Filters the output to only include defns (represented as lists) that
            are not empty after being filtered. Useful if you are trying to only
            see definitions of a certain part of speech. This way, you can
            enumerate over the returned values without having to worry if you're
            enumerating over an empty value.

        Returns
        -------
        list of list of str OR list of str
            If defnNum is set to 'all', it will include data from all
            definitions, returning a list of list of str, where each nested list
            is a single definition.
            If defnNum is set to an integer, it will return a list of str, where
            the str's are the filtered words for that single definition.
        """
        
        data = self._filter(mode='ant', defnNum=defnNum, filters=filters)

        # the word does not exist. return empty.
        if not data:
            return []
        
        if allowEmpty:
            return data
        else:
            return [d for d in data if len(d) > 0]

    def origin(self):
        """Gets the origin of a word.

        Returns
        -------
        str
            It's the paragraph that's on the right side of the page. It talks a
            bit about how the modern meaning of the word came to be.
        """
        return self.extra['origin']

    def examples(self):
        """Gets sentences the word is used in.

        Returns
        -------
        list of str
            Each str is a sentence the word is used in.
        """
        return self.extra['examples']
