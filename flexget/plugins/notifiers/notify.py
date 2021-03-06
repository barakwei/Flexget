from __future__ import unicode_literals, division, absolute_import
from builtins import *  # noqa pylint: disable=unused-import, redefined-builtin

import logging

import itertools
from flexget import plugin
from flexget.config_schema import one_or_more
from flexget.event import event
from flexget.utils.template import get_template

log = logging.getLogger('notify_entry')

ENTRY_CONTAINERS = ['entries', 'accepted', 'rejected', 'failed', 'undecided']

VIA_SCHEMA = {
    'type': 'array',
    'items': {
        'allOf': [
            {'$ref': '/schema/plugins?interface=notifiers'},
            {
                'maxProperties': 1,
                'error_maxProperties': 'Plugin options indented 2 more spaces than '
                                       'the first letter of the plugin name.',
                'minProperties': 1
            }
        ]
    }
}


class Notify(object):
    schema = {
        'type': 'object',
        'properties': {
            'entries': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string', 'default': '{{ title }}'},
                    'message': {
                        'type': 'string',
                        'default': '{% if series_name is defined %}'
                                   '{{ tvdb_series_name|d(series_name) }} '
                                   '{{series_id}} {{tvdb_ep_name|d('')}}'
                                   '{% elif imdb_name is defined %}'
                                   '{{imdb_name}} {{imdb_year}}'
                                   '{% elif title is defined %}'
                                   '{{ title }}'
                                   '{% endif %}'
                    },
                    'template': {'type': 'string'},
                    'what': one_or_more({'type': 'string', 'enum': ENTRY_CONTAINERS}),
                    'via': VIA_SCHEMA
                },
                'required': ['via'],
                'additionalProperties': False
            },
            'task': {
                'type': 'object',
                'properties': {
                    'title': {
                        'type': 'string',
                        'default': '[FlexGet] {{task.name}}:'
                                   '{%if task.failed %} {{task.failed|length}} failed entries.{% endif %}'
                                   '{% if task.accepted %} {{task.accepted|length}} new entries downloaded.{% endif %}'},
                    'template': {'type': 'string', 'default': 'default.template'},
                    'via': VIA_SCHEMA
                },
                'required': ['via'],
                'additionalProperties': False
            },
            'abort': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string', 'default': 'Task {{ task.name }} has aborted!'},
                    'message': {'type': 'string', 'default': 'Reason: {{ task.abort_reason }}'},
                    'via': VIA_SCHEMA
                },
                'required': ['via']
            }
        },
        'additionalProperties': False,
        'minProperties': 1,
        'error_minProperties': 'You must specify at least one of `entries` or `task` in your notify config.'
    }

    def prepare_config(self, config):
        if 'entries' in config:
            config['entries'].setdefault('what', ['accepted'])
            if not isinstance(config['entries']['what'], list):
                config['entries']['what'] = [config['entries']['what']]
        return config

    def on_task_notify(self, task, config):
        send_notification = plugin.get_plugin_by_name('notification_framework').instance.send_notification
        config = self.prepare_config(config)
        if 'entries' in config:
            entries = list(itertools.chain(*(getattr(task, what) for what in config['entries']['what'])))
            if not entries:
                log.debug('No entries to notify about.')
                return
            # If a file template is defined, it overrides message
            if config['entries'].get('template'):
                try:
                    message = get_template(config['entries']['template'], scope='entry')
                except ValueError:
                    raise plugin.PluginError('Cannot locate template on disk: %s' % config['entries']['template'])
            else:
                message = config['entries']['message']
            for entry in entries:
                send_notification(config['entries']['title'], message, config['entries']['via'],
                                  template_renderer=entry.render)
        if 'task' in config:
            if not (task.accepted or task.failed):
                log.verbose('No accepted or failed entries, not sending a notification.')
                return
            try:
                template = get_template(config['task']['template'], scope='task')
            except ValueError:
                raise plugin.PluginError('Cannot locate template on disk: %s' % config['task']['template'])
            send_notification(config['task']['title'], template, config['task']['via'], template_renderer=task.render)

    def on_task_abort(self, task, config):
        if 'abort' in config:
            send_notification = plugin.get_plugin_by_name('notification_framework').instance.send_notification
            if task.silent_abort:
                return
            log.debug('sending abort notification')
            send_notification(config['abort']['title'], config['abort']['message'], config['abort']['via'],
                              template_renderer=task.render)


@event('plugin.register')
def register_plugin():
    plugin.register(Notify, 'notify', api_ver=2)
