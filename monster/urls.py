# Copyright 2013: James Tunnicliffe
#
# This file is part of Need Input.
#
# Need Input is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Need Input is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Need Input.  If not, see <http://www.gnu.org/licenses/>.

from django.conf.urls import patterns, include, url
from django.conf import settings

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
from puke.views import Status
admin.autodiscover()

urlpatterns = patterns('',
    # Home
    url(r'^$', 'puke.views.home', name='home'),
    url(r'status/', Status.as_view(), name='status'),

    # Handle JS libs and CSS.
    url(r'^js/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': settings.JS_PATH}),
    url(r'^css/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': settings.CSS_PATH}),

    # Uncomment the admin/doc line below to enable admin documentation:
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),
)
