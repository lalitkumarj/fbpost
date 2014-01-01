#!/usr/bin/env python
#
# Copyright 2010 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
A barebones AppEngine application that uses Facebook for login.

1.  Make sure you add a copy of facebook.py (from python-sdk/src/)
    into this directory so it can be imported.
2.  Don't forget to tick Login With Facebook on your facebook app's
    dashboard and place the app's url wherever it is hosted
3.  Place a random, unguessable string as a session secret below in
    config dict.
4.  Fill app id and app secret.
5.  Change the application name in app.yaml.

"""
FACEBOOK_APP_ID = '1382784325310173'
FACEBOOK_APP_SECRET = '36a0bfc09d67dc011f7a90e99a94660f'

import facebook
import webapp2
import os
import jinja2
import urllib2
import urllib
import json
import random
import collections

from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext import db
from google.appengine.ext import ndb
from google.appengine.api import images
from webapp2_extras import sessions

config = {}
config['webapp2_extras.sessions'] = dict(secret_key='')
#upload_url_rpc = blobstore.create_upload_url_async('/upload')
#upload_url = upload_url_rpc.get_result()

class User(ndb.Model):
    id = ndb.StringProperty(required=True)
    created = ndb.DateTimeProperty(auto_now_add=True)
    updated = ndb.DateTimeProperty(auto_now=True)
    name = ndb.StringProperty(required=True)
    profile_url = ndb.StringProperty(required=True)
    access_token = ndb.StringProperty(required=True)

class Group(ndb.Model):
    name = ndb.StringProperty(required=True)
    url = ndb.StringProperty(required=True)

class Post(ndb.Model):
    status = ndb.StringProperty(required=True)
    post_url = ndb.StringProperty(required=True)
    picture_url = ndb.StringProperty(required=True)
    container = ndb.StringProperty(required=True)
    date = ndb.DateTimeProperty(auto_now_add=True)
    groups = ndb.StructuredProperty(Group, repeated=True)

class BaseHandler(webapp2.RequestHandler):
    """Provides access to the active Facebook user in self.current_user

    The property is lazy-loaded on first access, using the cookie saved
    by the Facebook JavaScript SDK to determine the user ID of the active
    user. See http://developers.facebook.com/docs/authentication/ for
    more information.
    """
    @property
    def current_user(self):
        if self.session.get("user"):
            # User is logged in
            return self.session.get("user")
        else:
            # Either used just logged in or just saw the first page
            # We'll see here
            cookie = facebook.get_user_from_cookie(self.request.cookies,
                                                   FACEBOOK_APP_ID,
                                                   FACEBOOK_APP_SECRET)
            if cookie:
                # Okay so user logged in.
                # Now, check to see if existing user
                #user = User.get_by_key_name(cookie["uid"])
                user = User.get_by_id(cookie["uid"])
                
                if not user:
                    # Not an existing user so get user info
                    graph = facebook.GraphAPI(cookie["access_token"])
                    profile = graph.get_object("me")
                    user = User(
                        key_name=str(profile["id"]),
                        id=str(profile["id"]),
                        name=profile["name"],
                        profile_url=profile["link"],
                        access_token=cookie["access_token"]                        
                    )
                    user.put()
                elif user.access_token != cookie["access_token"]:
                    user.access_token = cookie["access_token"]
                    user.put()
                # User is now logged in
                self.session["user"] = dict(
                    name=user.name,
                    profile_url=user.profile_url,
                    id=user.id,
                    access_token=user.access_token
                )
                return self.session.get("user")
        return None

    def dispatch(self):
        """
        This snippet of code is taken from the webapp2 framework documentation.
        See more at
        http://webapp-improved.appspot.com/api/webapp2_extras/sessions.html

        """
        self.session_store = sessions.get_store(request=self.request)
        try:
            webapp2.RequestHandler.dispatch(self)
        finally:
            self.session_store.save_sessions(self.response)

    @webapp2.cached_property
    def session(self):
        """
        This snippet of code is taken from the webapp2 framework documentation.
        See more at
        http://webapp-improved.appspot.com/api/webapp2_extras/sessions.html
fac
        """
        return self.session_store.get_session()
    
    @property
    def graph(self):
        """Returns a Graph API client for the current user."""
        if not hasattr(self, "_graph"):
            if self.current_user:
                self._graph = facebook.GraphAPI(self.current_user['access_token'])
            else:
                self._graph = facebook.GraphAPI()
        return self._graph



class HomeHandler(BaseHandler):
    def get(self):        
        if self.current_user != None:
            self.redirect("/portal")
        else:
            self.redirect("/login")

class LoginHandler(BaseHandler):
    def get(self):
        if self.current_user:
            self.redirect("/portal")
        else:
            template = jinja_environment.get_template('login.html')
            self.response.out.write(template.render(dict(
                        facebook_app_id=FACEBOOK_APP_ID,
                        current_user=self.current_user
                        )))
        
class ServiceHandler(BaseHandler):
    def get(self):
        if self.current_user != None: 
            template = jinja_environment.get_template('form.html')
            upload_url = blobstore.create_upload_url('/upload')
            pages = self.graph.get_connections("me","accounts")
            groups = self.graph.get_connections("me","groups")
            
            self.response.out.write(template.render(dict(
                        facebook_app_id=FACEBOOK_APP_ID,
                        current_user=self.current_user,
                        pages=pages['data'],
                        groups=groups['data'],
                        url = upload_url 
                        )))
        else:
            self.redirect("/")
        
    def post(self):
        description = self.request.get('description_input')
        
        select_pages = self.request.get('select_pages', allow_multiple=True)
        select_groups = self.request.get('select_groups',allow_multiple=True)
        
        blob_key = self.request.get('imagekey')
        blob_reader = blobstore.BlobReader(blob_key,buffer_size=1048576)

        pages = self.graph.get_connections("me","accounts")['data']
        page_tokens = dict([(page['id'], page['access_token']) for page in pages])
        page_names = dict([(page['id'], page['name']) for page in pages])

        groups = self.graph.get_connections("me","groups")['data']
        group_names = dict([(group['id'], group['name']) for group in groups])
        
#TODO: You should only get one page!
        for page_id in select_pages:
            page_posted_id =  self.graph.put_photo(blob_reader, description, album_id=page_id, access_token=page_tokens[page_id])['id']
    
        for group_id in select_groups:
            blob_reader = blobstore.BlobReader(blob_key,buffer_size=1048576)
            posted_id =  self.graph.put_photo(blob_reader, description, album_id=group_id)['post_id']
            post = Post(parent=ndb.Key("User", self.current_user['id']),
                        post_url=posted_id, 
                        picture_url=images.get_serving_url(blob_key),
                        container = page_names[page_id],
                        status = "active",
                        groups = [Group(name=group_names[g], url=posted_id) for g in select_groups])  
            post.put()

        
        self.redirect('/redirect?submit_post')


class ManageHandler(BaseHandler):
    def get(self):
        if self.current_user != None: 
            template = jinja_environment.get_template('manage.html')
            query = Post.query(ancestor=ndb.Key("User",self.current_user['id']))
#need a list of posts. get this list of posts by sorting by page_id. a post should be a dictionary . has a group field that has a list of 
            posts = [dict([('post_url',"http://facebook.com/"+q.post_url), 
                           ('key',str(q.key.pairs()[0][1]) +"_"+ str(q.key.pairs()[1][1])),
                           ('date', q.date), 
                           ('status', q.status),
                           ('container', q.container),
                           ('picture_url', q.picture_url),
                           ('groups',dict([(group.name, "http://facebook.com/"+group.url) for group in q.groups ]) )] ) for q in query.iter() if q.status=="active"]
            self.response.out.write(template.render(dict(
                        facebook_app_id=FACEBOOK_APP_ID,
                        current_user=self.current_user,
                        posts = posts
                        )))
        else:
            self.redirect("/")
    
    def post(self):
        keys = self.request.get("postkey").split("_")
        post = ndb.Key("User", keys[0], "Post",int(keys[1]) ).get()
        post.status = "delete"
        post.put()
        for g in post.groups:
            self.graph.delete_object(g.url)

        
class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):        
    def post(self):
        upload_files = self.get_uploads('files[]')
        blob_info = upload_files[0]
        obj = {
            'upload_image_key': str(blob_info.key()) 
            } 
        self.redirect("/redirect?"+urllib.urlencode(obj))
        

class RedirectHandler(BaseHandler):    
    def get(self):
        if self.request.get('upload_image_key') != '': 
            obj = {
                'key': self.request.get('upload_image_key')
                } 
            print "make a key"+obj['key']
            self.response.headers['Content-Type'] = 'application/json'   
            self.response.out.write(json.dumps(obj))
        elif self.request.get('submit_post') != '':
            self.redirect('/end')

class PortalHandler(BaseHandler):
    def get(self):
        if self.current_user != None:
            template = jinja_environment.get_template('portal.html')
            self.response.out.write(template.render(dict(
                    facebook_app_id=FACEBOOK_APP_ID,
                    current_user=self.current_user)))
        else:
            self.redirect("/")

class EndHandler(BaseHandler):
    def get(self):
        if self.current_user != None:
            template = jinja_environment.get_template('end.html')
            self.response.out.write(template.render(dict(
                    facebook_app_id=FACEBOOK_APP_ID,
                    current_user=self.current_user)))
        else:
            self.redirect("/")

class LogoutHandler(BaseHandler):
    def get(self):
        if self.current_user is not None:
            self.session['user'] = None
            cookie = self.response.delete_cookie("fbsr_"+FACEBOOK_APP_ID)
            self.response.delete_cookie("session")
        self.redirect("/")

jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname("templates/base.html")) , autoescape=True, extensions=['jinja2.ext.autoescape'])

application = webapp2.WSGIApplication(
    [('/', HomeHandler), ('/login', LoginHandler), ('/portal', PortalHandler) , ('/manage', ManageHandler), ('/manage/deletepost', ManageHandler), ('/upload',UploadHandler), ('/service', ServiceHandler),('/service/post',ServiceHandler), ('/redirect?',RedirectHandler), ('/logout', LogoutHandler), ('/end',EndHandler)],
    debug=True,
    config=config
)


        # for group in select_groups:
        #     self.graph.put_wall_post(description, {"link":"http://facebook.com/%s"%(posted_id),"picture":images.get_serving_url(blob_key)}, group)
