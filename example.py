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
FACEBOOK_APP_ID = "1382784325310173"
FACEBOOK_APP_SECRET = "36a0bfc09d67dc011f7a90e99a94660f"

import facebook
import webapp2
import os
import jinja2
import urllib2

from google.appengine.ext import db
from webapp2_extras import sessions

config = {}
config['webapp2_extras.sessions'] = dict(secret_key='')


class User(db.Model):
    id = db.StringProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)
    name = db.StringProperty(required=True)
    profile_url = db.StringProperty(required=True)
    access_token = db.StringProperty(required=True)


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
                user = User.get_by_key_name(cookie["uid"])
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
        if self.current_user:
            self.redirect("/form")
        else:
            self.redirect("/login")

class LoginHandler(BaseHandler):
    def get(self):
        template = jinja_environment.get_template('templates/login.html')
        self.response.out.write(template.render(dict(
                    facebook_app_id=FACEBOOK_APP_ID,
                    current_user=self.current_user
                    )))
        
class FormHandler(BaseHandler):
    def get(self):
        template = jinja_environment.get_template('templates/form.html')
        pages = self.graph.get_connections("me","accounts")
        groups = self.graph.get_connections("me","groups")
        
        self.response.out.write(template.render(dict(
                    facebook_app_id=FACEBOOK_APP_ID,
                    current_user=self.current_user,
                    pages=pages['data'],
                    groups=groups['data']
                    )))
        
    def post(self):
        description = self.request.get('description_input')
        select_pages = self.request.get('select_pages',allow_multiple=True)
        select_groups = self.request.get('select_groups',allow_multiple=True)
#Which page_id to take? Need to reject more then one selection client side? Radio box?
        # for page in select_pages:
        #     page_id = self.graph.put_wall_post(description, att{"picture":"facebook.com/10100739842477767"}, page)['id']
        # for group in select_groups:
        #     print self.graph.put_wall_post(description, {}, group)
        
        #

class ImageHandler(BaseHandler):
        
    def post(self):
        image  = self.request.POST.get("files[]").file
        print self.graph.put_photo(image,"This is a bit of a long description of this image. ope you like it", "10100739842477767")


#Which page_id to take? Need to reject more then one selection client side? Radio box?


    # graph = facebook.GraphAPI(self.current_user['access_token'])
    #         print "groups "+str(graph.get_connections("me","groups"))
      
    # def post(self):
    #     url = self.request.get('url')
    #     file = urllib2.urlopen(url)
    #     graph = facebook.GraphAPI(self.current_user['access_token'])
    #     response = graph.put_photo(file, "Test Image")
    #     photo_url = ("http://www.facebook.com/"
    #                  "photo.php?fbid={0}".format(response['id']))
    #     self.redirect(str(photo_url))


class LogoutHandler(BaseHandler):
    def get(self):
        if self.current_user is not None:
            self.session['user'] = None
        self.redirect("/login")

jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)) , autoescape=True, extensions=['jinja2.ext.autoescape'])

application = webapp2.WSGIApplication(
    [('/', HomeHandler), ('/login', LoginHandler), ('/logout', LogoutHandler), ('/form', FormHandler),('/form/post',FormHandler),('/form/image',ImageHandler)],
    debug=True,
    config=config
)
