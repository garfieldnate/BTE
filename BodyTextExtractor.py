#!/usr/bin/env python
from __future__ import print_function

import logging
import sys

logger = logging.getLogger(__name__)

if sys.version_info >= (3, 0):
    py2 = False
else:
    py2 = True

if py2:
    from HTMLParser import HTMLParser
else:
    from html.parser import HTMLParser

TAG_TOKEN = 1
DATA_TOKEN = -1


class HtmlTokenParser(HTMLParser):
    def error(self, message):
        logger.error(message)

    # creates a list of tokens (tags and text) and
    # and classified tokens (1 for tags, -1 for text)
    def __init__(self, verbose=0):
        self.tokens = []
        self.binary_tokens = []
        self.body_start_index = 0
        HTMLParser.__init__(self)

    def handle_data(self, data):
        # TODO: will not work for non-space languages
        for t in data.split():
            self.tokens.append(t)
            self.binary_tokens.append(-1)

    def handle_starttag(self, tag, attrs):
        self.binary_tokens.append(TAG_TOKEN)
        self.tokens.append("<" + tag + ">")
        if tag == 'body':
            self.body_start_index = len(self.tokens)

    def handle_endtag(self, tag):
        self.tokens.append("<\\" + tag + ">")
        self.binary_tokens.append(TAG_TOKEN)


class HtmlBodyTextExtractor(HtmlTokenParser):
    def __init__(self):
        HtmlTokenParser.__init__(self)
        self.encoded = [0]
        self.total_tokens_before = [0]
        self.lookup0N = [0]
        self.lookupN0 = [0]
        self.body_txt = ""

    def close(self):
        HtmlTokenParser.close(self)
        self._encode_binary_tokens()
        self._initialise_lookups()

    def _encode_binary_tokens(self):
        i = 0
        for token in self.binary_tokens:
            if abs(token + self.encoded[i]) < abs(self.encoded[i]):
                self.encoded.append(0)
                self.total_tokens_before.append(self.total_tokens_before[-1])
                i += 1
            self.encoded[i] = self.encoded[i] + token
            self.total_tokens_before[i] = self.total_tokens_before[i] + 1
        # total_tokens_before works better in the rest of the class if we shift all values up one index
        self.total_tokens_before.insert(0, 0)

    def _initialise_lookups(self):
        t = 0
        for token in self.encoded:
            if token > 0:
                t = t + token
            self.lookup0N.append(t)
        self.encoded.reverse()
        t = 0
        for token in self.encoded:
            if token > 0:
                t = t + token
            self.lookupN0.append(t)
        self.encoded.reverse()
        self.lookupN0.reverse()
        del (self.lookupN0[0])  # will never need these values
        del (self.lookup0N[-1])

    '''
    This method has been modified to be in O(1).
    This version of the method works with the assumption that all nodes are
    either text or tags. Since we can quickly find out the number of tags
    that have occured upto a given region, and the number of total tags up
    to that region, we can quickly calculate the number of text nodes that
    have occured upto that region.

    The original method is available as _objective_fcn_old
    '''

    def _objective_fcn(self, i, j):
        tags_to_i = self.lookup0N[i]
        tags_after_j = self.lookupN0[j]

        text_to_i = self.total_tokens_before[i] - tags_to_i
        text_to_j = self.total_tokens_before[j] - self.lookup0N[j]

        text_between_i_j = text_to_j - text_to_i
        return_val = tags_to_i + tags_after_j + text_between_i_j
        return return_val

    '''
    The original method, which is in O(n)
    '''

    def _objective_fcn_old(self, i, j):
        return_val = self.lookup0N[i] + self.lookupN0[j]
        for token in self.encoded[i:j]:
            if token < 0:
                return_val = return_val - token
        return return_val

    @staticmethod
    def _is_tag(s):
        if s[0] == '<' and s[-1] == '>':
            return 1
        else:
            return 0

    '''
    Method which uses the modified version of _objective_fcn, this function is in O(n^2)
    This method has also been modified to improve the finding of the 'start' and 'end' variables
    Finally, body_text now uses the join method for building the output string
    '''

    def body_text(self):
        self.body_txt = ""
        obj_max = 0
        i_max = self.body_start_index
        j_max = len(self.encoded) - 1
        for i in range(self.body_start_index, len(self.encoded) - 1):
            if self.encoded[i] > 0:
                continue
            for j in range(i, len(self.encoded)):
                if self.encoded[j] > 0:
                    continue
                obj = self._objective_fcn(i, j)
                if obj > obj_max:
                    obj_max = obj
                    i_max = i
                    j_max = j
        start = self.total_tokens_before[i_max]
        end = self.total_tokens_before[j_max]

        self.body_txt = " ".join(txt for txt in self.tokens[start:end] if not self._is_tag(txt))

        return self.body_txt

    def summary(self, start=0, length=255):
        if not self.body_txt:
            self.body_text()
        return self.body_txt[start:(start + length)]

    def full_text(self):
        ft = " ".join(txt for txt in self.tokens if not self._is_tag(txt))
        return ft


if __name__ == '__main__':
    html = open(sys.argv[1]).read()
    p = HtmlBodyTextExtractor()
    p.feed(html)
    p.close()
    x = p.body_text()
    print("\nBody text:\n", p.body_text())

# (c) 2001 Aidan Finn
# Released under the terms of the GNU GPL
