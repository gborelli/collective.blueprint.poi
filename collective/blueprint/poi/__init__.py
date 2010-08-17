import urllib
from OFS.Image import File

from zope.interface import classProvides, implements
from collective.transmogrifier.interfaces import ISectionBlueprint
from collective.transmogrifier.interfaces import ISection
from collective.transmogrifier.utils import defaultMatcher

from Products.Poi.content.PoiIssue import PoiIssue
from Products.Poi.adapters import IResponseContainer
from Products.Poi.adapters import Response

default_response_properties = ['mimetype', 'changes',
            'rendered_text', 'creator', 'text',
            'attachment', 'date', 'type']

import logging
zope_logger = logging.getLogger('collective.blueprint.poi')


class ResponseExport(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.root = transmogrifier.context.unrestrictedTraverse(options.get('source_root', None))
        self.pathkey = defaultMatcher(options, 'path-key', name, 'path')
        self.response_properties = options.get('response_properties', '').splitlines()
        if self.response_properties == []:
            self.response_properties = default_response_properties
        self.response_properties.extend(['attachment_filename', 'attachment_url'])

    def __iter__(self):
        for item in self.previous:
            keys = item.keys()
            pathkey = self.pathkey(*keys)[0]

            if not pathkey:
                yield item; continue
            path = item[pathkey]

            obj = self.root.unrestrictedTraverse(path.lstrip('/'), None)
            if obj is None:  # path doesn't exist
                yield item; continue

            if isinstance(obj, PoiIssue):
                container = IResponseContainer(obj)
                item['poi_responses'] = []
                for id, response_obj in enumerate(container):
                    response = {}
                    for prop in self.response_properties:
                        # changes is a persistent list, I'll convert to list
                        if prop == 'changes':
                            response[prop] = [i for i in getattr(response_obj, prop, None)]
                        else:
                            response[prop] = getattr(response_obj, prop, None)
                    attachment_info = self.getAttachment(id, response_obj, obj.absolute_url())
                    if attachment_info:
                        response['attachment_filename'] = attachment_info[0]
                        response['attachment_url'] = attachment_info[1]
                    item['poi_responses'].append(response)
            yield item

    def getAttachment(self, id, response, base_url):
        attachment = response.attachment
        if attachment is None:
            return None
        filename = getattr(attachment, 'filename', attachment.getId())
        url= '/@@poi_response_attachment?response_id=' + str(id)
        return filename, url



class ResponseImport(object):
    classProvides(ISectionBlueprint)
    implements(ISection)

    def __init__(self, transmogrifier, name, options, previous):
        self.previous = previous
        self.context = transmogrifier.context
        self.pathkey = defaultMatcher(options, 'path-key', name, 'path')
        self.orig_plone_url = options.get('orig_plone_url', None)

    def __iter__(self):
        for item in self.previous:
            keys = item.keys()
            pathkey = self.pathkey(*keys)[0]

            if not pathkey or ('poi_responses' not in keys):
                yield item; continue
            path = item[pathkey]

            obj = self.context.unrestrictedTraverse(path.lstrip('/'), None)
            if obj is None:  # path doesn't exist
                yield item; continue

            if isinstance(obj, PoiIssue):
                container = IResponseContainer(obj)
                i = 0
                for response in item['poi_responses']:
                    attachment_filename = response.pop('attachment_filename')
                    attachment_url = response.pop('attachment_url')

                    to_add = True
                    try:
                        r_obj = container[i]
                        to_add = False
                    except IndexError:
                        r_obj = Response(response.get('text',''))

                    for k, v in response.items():
                        setattr(r_obj, k, v)

                    if attachment_filename and attachment_url:
                        # import pdb; pdb.set_trace()
                        attachment = self.setAttachment(attachment_filename,
                            self.orig_plone_url + '/'.join(obj.getPhysicalPath()[2:]) + attachment_url)
                        #self.orig_plone_url + '/' + attachment_url)
                        if attachment:
                            r_obj.attachment = attachment

                    if to_add:
                        container.add(r_obj)
                    i += 1

            yield item

    def setAttachment(self, attachment_filename, attachment_url):
        try:
            response = urllib.urlopen(attachment_url)
            file_data = response.read()
            #import pdb; pdb.set_trace()
            if not file_data or 'Not Found' in file_data: 
                zope_logger.warning("Errore nello scaricare il file: %s" % attachment_url)
            file_data = File(attachment_filename, attachment_filename, file_data)
            # fileData.filename = attachment_filename
            return file_data
        except:
            zope_logger.warning("Errore nello scaricare il file: %s" % attachment_url)
