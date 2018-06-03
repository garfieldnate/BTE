#!/usr/bin/env python
from __future__ import print_function

import logging
import re
import sys

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

if sys.version_info < (3, 0):
    py2 = True
else:
    py2 = False

if py2:
    from HTMLParser import HTMLParser
    # Fixes unicode problems; see https://stackoverflow.com/a/21190382/474819
    reload(sys)
    sys.setdefaultencoding('utf8')
else:
    from html.parser import HTMLParser

TAG_TOKEN = 1
DATA_TOKEN = -1
LINEBREAK_ELEMENTS = {'address', 'article', 'aside', 'blockquote', 'canvas', 'dd', 'div', 'dl', 'dt', 'fieldset',
                      'figcaption', 'figure', 'footer', 'form', 'h1', 'h6', 'header', 'hr', 'li', 'main', 'nav',
                      'noscript', 'ol', 'output', 'p', 'pre', 'section', 'table', 'tfoot', 'ul', 'video', 'br'}
MULTI_SPACES_REGEX = re.compile("[ ]+")


class HtmlTokenParser(HTMLParser):
    def error(self, message):
        logger.error(message)

    # creates a list of tokens (tags and text) and
    # and classified tokens (1 for tags, -1 for text)
    def __init__(self, verbose=0):
        self.tokens = []
        self.binary_tokens = []
        self.body_start_index = 0
        self.break_next = False
        HTMLParser.__init__(self)

    def handle_data(self, data):
        # TODO: will not work for non-space languages; perhaps store a negative number indicating the number of characters?
        tokens = data.split()
        # add back line breaks to preserve some of the document structure
        if self.break_next:
            if len(tokens):
                tokens[0] = "\n" + tokens[0]
            self.break_next = False
        for t in tokens:
            self.tokens.append(t)
            self.binary_tokens.append(-1)

    def handle_starttag(self, tag, attrs):
        self.binary_tokens.append(TAG_TOKEN)
        self.tokens.append("<" + tag + ">")
        if tag == 'body':
            self.body_start_index = len(self.tokens)

    def handle_endtag(self, tag):
        self.tokens.append("<\\" + tag + ">")
        if tag in LINEBREAK_ELEMENTS:
            self.break_next = True
        self.binary_tokens.append(TAG_TOKEN)


class HtmlBodyTextExtractor(HtmlTokenParser):
    def __init__(self):
        HtmlTokenParser.__init__(self)
        self.encoded = [0]
        self.total_tokens_before = [0]
        self.num_tags_until = [0]
        self.num_tags_after = [0]
        self.body_txt = ""

    def feed(self, text):
        text = self._remove_unreadable(text)
        HtmlTokenParser.feed(self, text)

    @staticmethod
    def _remove_unreadable(text):
        """Remove unreadable blocks (head, style, script) from the text.
        This is a necessary pre-processing step because the simple objective function often
        picks long script blocks."""
        soup = BeautifulSoup(text, 'lxml')
        for unreadable in soup.find_all(['head', 'script', 'style']):
            unreadable.extract()
        return str(soup)

    def close(self):
        HtmlTokenParser.close(self)
        self._count_cumulative_tokens()
        self._count_cumulative_tags()

    def _count_cumulative_tokens(self):
        """Sets the following variables in self:
        encoded: a list of numbers indicating the number of successive tokens of a single type;
            positive values will indicate tags, negative will indicate data.
        total_tokens_before: indicates the total number of tokens before an entry in encoded.
        """
        i = 0
        for token in self.binary_tokens:
            # find boundaries between strings of tags and strings of data
            if abs(token + self.encoded[i]) < abs(self.encoded[i]):
                self.encoded.append(0)
                self.total_tokens_before.append(self.total_tokens_before[-1])
                i += 1
            self.encoded[i] += token
            self.total_tokens_before[i] += 1
        # total_tokens_before works better in the rest of the class if we shift all values up one index
        self.total_tokens_before.insert(0, 0)

    def _count_cumulative_tags(self):
        """Sets the following variables in self:
        num_tags_until: indicates at each position how many data tokens were seen up to that point,
            starting at the beginning of the document.
        num_tags_after: same as num_tags_until, but counts the tags from that point until the
            end of the document.
        """
        t = 0
        for token in self.encoded:
            if token > 0:
                t += token
            self.num_tags_until.append(t)
        t = 0
        for token in reversed(self.encoded):
            if token > 0:
                t += token
            self.num_tags_after.append(t)
        self.num_tags_after.reverse()
        # will never need these values
        del (self.num_tags_after[0])
        del (self.num_tags_until[-1])

    def _objective_fcn(self, i, j):
        """Returns the number of tags that have been excluded plus the number of words that have been included"""
        tags_after_j = self.num_tags_after[j]

        text_to_i = self.total_tokens_before[i] - self.num_tags_until[i]
        text_to_j = self.total_tokens_before[j] - self.num_tags_until[j]

        text_between_i_j = text_to_j - text_to_i
        return_val = self.num_tags_until[i] + tags_after_j + text_between_i_j
        return return_val

    @staticmethod
    def _is_tag(s):
        return s[0] == '<' and s[-1] == '>'

    def body_text(self):
        # memoize result, since it's expensive
        if self.body_txt:
            return self.body_txt
        (start, end) = self._find_optimal_span()

        text = " ".join(txt for txt in self.tokens[start:end] if not self._is_tag(txt))
        # get rid of repeated spaces
        text = MULTI_SPACES_REGEX.sub(' ', text)
        # strip each line
        text = '\n'.join([t.strip() for t in text.split('\n')])

        self.body_txt = text
        return self.body_txt

    def _find_optimal_span(self):
        """Finds the longest text section which excludes the most tags using an O(N^2) exhaustive search of all
        eligible text spans."""
        score_max = 0
        i_max = self.body_start_index
        j_max = len(self.encoded) - 1
        for i in range(self.body_start_index, len(self.encoded) - 1):
            if self.encoded[i] > 0:
                continue
            for j in range(i, len(self.encoded)):
                if self.encoded[j] > 0:
                    continue
                score = self._objective_fcn(i, j)
                if score > score_max:
                    score_max = score
                    i_max = i
                    j_max = j
        start = self.total_tokens_before[i_max]
        end = self.total_tokens_before[j_max]
        return start, end

    def full_text(self):
        ft = " ".join(txt for txt in self.tokens if not self._is_tag(txt))
        return ft


if __name__ == '__main__':
    html = open(sys.argv[1]).read()
    p = HtmlBodyTextExtractor()
    p.feed(html)
    p.close()
    print(p.body_text())

# (c) 2001 Aidan Finn
# Released under the terms of the GNU GPL
