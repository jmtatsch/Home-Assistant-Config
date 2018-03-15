"""
Support for the Nokia Health API.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.nokia_health/
"""
import os
import logging
import datetime
import time

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import MASS_KILOGRAMS
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv
from homeassistant.util.json import load_json, save_json
from homeassistant.util import Throttle

REQUIREMENTS = ['nokia==0.4.0']

_CONFIGURING = {}
_LOGGER = logging.getLogger(__name__)

ATTR_ACCESS_TOKEN = 'access_token'
ATTR_REFRESH_TOKEN = 'refresh_token'
ATTR_API_KEY = 'apy_key'
ATTR_API_SECRET = 'api_secret'
ATTR_CLIENT_ID: 'consumer_key'
ATTR_CLIENT_SECRET: 'consumer_secret'
ATTR_LAST_SAVED_AT = 'last_saved_at'

CONF_MONITORED_RESOURCES = 'monitored_resources'
CONF_CLOCK_FORMAT = 'clock_format'
CONF_ATTRIBUTION = 'Data provided by health.nokia.com'

DEPENDENCIES = ['http']

NOKIA_HEALTH_CONFIG_FILE = 'nokia_health.conf'
NOKIA_HEALTH_DEFAULT_RESOURCES = ['body/weight']
NOKIA_HEALTH_AUTH_CALLBACK_PATH = 'https://developer.health.nokia.com/en/partner/add'
NOKIA_HEALTH_AUTH_START = 'https://developer.health.nokia.com/en/partner/add'  # FIXME: look this up
SCAN_INTERVAL = datetime.timedelta(minutes=30)

DEFAULT_CONFIG = {
    'access_token': 'your_access_token',
    'access_token_secret': 'your_access_token_secret',
    'consumer_key': 'your_consumer_key',
    'consumer_secret': 'your_consumer_secret',
    'user_id': 'your_user_id'
}

NOKIA_HEALTH_RESOURCES_LIST = {
    'body/bmi': ['BMI', 'BMI', 'human'],
    'body/fat': ['Body Fat', '%', 'human'],
    'body/weight': ['Weight', '', 'human']
}

NOKIA_HEALTH_MEASUREMENTS = {
    'en_US': {
        'duration': 'ms',
        'distance': 'mi',
        'elevation': 'ft',
        'height': 'in',
        'weight': 'lbs',
        'body': 'in',
        'liquids': 'fl. oz.',
        'blood glucose': 'mg/dL',
        'battery': '',
    },
    'en_GB': {
        'duration': 'milliseconds',
        'distance': 'kilometers',
        'elevation': 'meters',
        'height': 'centimeters',
        'weight': 'stone',
        'body': 'centimeters',
        'liquids': 'milliliters',
        'blood glucose': 'mmol/L',
        'battery': '',
    },
    'metric': {
        'duration': 'milliseconds',
        'distance': 'kilometers',
        'elevation': 'meters',
        'height': 'centimeters',
        'weight': 'kilograms',
        'body': 'centimeters',
        'liquids': 'milliliters',
        'blood glucose': 'mmol/L',
        'battery': '',
    }
}

BATTERY_LEVELS = {
    'High': 100,
    'Medium': 50,
    'Low': 20,
    'Empty': 0
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_MONITORED_RESOURCES, default=NOKIA_HEALTH_DEFAULT_RESOURCES):
        vol.All(cv.ensure_list, [vol.In(NOKIA_HEALTH_RESOURCES_LIST)]),
    vol.Optional(CONF_CLOCK_FORMAT, default='24H'):
        vol.In(['12H', '24H'])
})


def request_app_setup(hass, config, add_devices, config_path):
    """Assist user with configuring the Nokia Health application."""
    configurator = hass.components.configurator

    # pylint: disable=unused-argument
    def configuration_callback(callback_data):
        """Handle configuration updates."""
        config_path = hass.config.path(NOKIA_HEALTH_CONFIG_FILE)
        if os.path.isfile(config_path):
            config_file = load_json(config_path)
            if config_file == DEFAULT_CONFIG:
                error_msg = ("You didn't correctly modify nokia_health.conf",
                             " please try again")
                configurator.notify_errors(_CONFIGURING['nokia_health'],
                                           error_msg)
            else:
                setup_platform(hass, config, add_devices)
        else:
            setup_platform(hass, config, add_devices)

    description = """Please create a Nokia Health developer app at: {}
                       They will provide you a API key and secret.
                       These need to be saved into the file located at: {}.
                       Then come back here and hit the below button.
                       """.format(NOKIA_HEALTH_AUTH_CALLBACK_PATH, config_path)

    submit = "I have saved my Client ID and Client Secret into nokia_health.conf."

    _CONFIGURING['nokia_health'] = configurator.request_config(
        'Nokia Health', configuration_callback,
        description=description, submit_caption=submit,
        description_image="/static/images/config_nokia_health_app.png"
    )


def request_oauth_completion(hass):
    """Request user to complete the Nokia Health OAuth2 flow."""
    configurator = hass.components.configurator
    if "nokia_health" in _CONFIGURING:
        configurator.notify_errors(
            _CONFIGURING['nokia_health'], "Failed to register, please try again.")

        return

    # pylint: disable=unused-argument
    def configuration_callback(callback_data):
        """Handle configuration updates."""

    start_url = '{}{}'.format(hass.config.api.base_url, NOKIA_HEALTH_AUTH_START)

    description = "Please authorize Nokia Health by visiting {}".format(start_url)

    _CONFIGURING['nokia_health'] = configurator.request_config(
        'Nokia_Health', configuration_callback,
        description=description,
        submit_caption="I have authorized Nokia Health."
    )


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Nokia Health sensor."""
    config_path = hass.config.path(NOKIA_HEALTH_CONFIG_FILE)
    if os.path.isfile(config_path):
        config_file = load_json(config_path)
        if config_file == DEFAULT_CONFIG:
            request_app_setup(
                hass, config, add_devices, config_path)
            return False
    else:
        config_file = save_json(config_path, DEFAULT_CONFIG)
        request_app_setup(hass, config, add_devices, config_path)
        return False

    if "nokia_health" in _CONFIGURING:
        hass.components.configurator.request_done(_CONFIGURING.pop("nokia_health"))

    data_manager = NokiaHealthDataManager(config_file)

    devices = []
    valid_attributes = ["weight", "fat_ratio", "fat_free_mass", "fat_mass_weight"]
    for attribute in valid_attributes:
        device = NokiaHealthSensor(data_manager, config_file.get("user_id"),
                                   attribute, MASS_KILOGRAMS)
        devices.append(device)
    add_devices(devices)
    return True


class NokiaHealthAuthCallbackView(HomeAssistantView):
    """Handle OAuth finish callback requests."""

    requires_auth = False

    def __init__(self, config, add_devices, oauth):
        """Initialize the OAuth callback view."""
        self.config = config
        self.add_devices = add_devices
        self.oauth = oauth

    @callback
    def get(self, request):
        """Finish OAuth callback request."""
        from oauthlib.oauth2.rfc6749.errors import MismatchingStateError
        from oauthlib.oauth2.rfc6749.errors import MissingTokenError
        from nokia import NokiaAuth

        hass = request.app['hass']
        data = request.query

        response_message = """Nokia Health has been successfully authorized!
        You can close this window now!"""

        result = None
        if data.get('code') is not None:
            oauth = NokiaAuth(self.config.get(ATTR_API_KEY), self.config.get(ATTR_API_SECRET))
            redirect_uri = oauth.get_authorize_url()

            try:
                result = self.oauth.fetch_access_token(data.get('code'),
                                                       redirect_uri)

                print(result)
                oauth_verifier = result.get('oauth_verifier')
                print(oauth_verifier)
            except MissingTokenError as error:
                _LOGGER.error("Missing token: %s", error)
                response_message = """Something went wrong when
                attempting authenticating with Nokia Health. The error
                encountered was {}. Please try again!""".format(error)
            except MismatchingStateError as error:
                _LOGGER.error("Mismatched state, CSRF error: %s", error)
                response_message = """Something went wrong when
                attempting authenticating with Nokia Health. The error
                encountered was {}. Please try again!""".format(error)
        else:
            _LOGGER.error("Unknown error when authing")
            response_message = """Something went wrong when
                attempting authenticating with Nokia Health.
                An unknown error occurred. Please try again!
                """

        if result is None:
            _LOGGER.error("Unknown error when authing")
            response_message = """Something went wrong when
                attempting authenticating with Nokia Health.
                An unknown error occurred. Please try again!
                """

        html_response = """<html><head><title>Nokia Health Auth</title></head>
        <body><h1>{}</h1></body></html>""".format(response_message)

        if result:
            config_contents = {
                ATTR_ACCESS_TOKEN: result.get('access_token'),
                ATTR_REFRESH_TOKEN: result.get('refresh_token'),
                ATTR_CLIENT_ID: self.oauth.client_id,
                ATTR_CLIENT_SECRET: self.oauth.client_secret,
                ATTR_LAST_SAVED_AT: int(time.time())
            }
        save_json(hass.config.path(NOKIA_HEALTH_CONFIG_FILE), config_contents)

        hass.async_add_job(setup_platform, hass, self.config, self.add_devices)

        return html_response


class NokiaHealthSensor(Entity):
    """Implementation of a Nokia Health sensor."""

    def __init__(self, data_manager, user_id, attribute, unit):
        """Initialize the Nokia Health sensor."""
        self._name = '{} {}'.format(user_id, attribute)
        self._data_manager = data_manager
        self._state = None
        self._attribute = attribute
        self._unit_of_measurement = unit
        self._icon = None
        self.update()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        pass

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attribute

    def update(self):
        """Get the latest data from the NokiaHealthDataManager and update the states."""
        if self._data_manager._update() is None:
            _LOGGER.debug("No new values, throtteling is active")
        print(self._attribute, ': ', getattr(self._data_manager.data[0], self._attribute))
        _LOGGER.info("%s for key %s" % (getattr(self._data_manager.data[0], self._attribute), self._attribute))
        self._state = 23

class NokiaHealthDataManager(object):
    """Manage data from Nokia Health. Bundles downloading all attributes for a measurement."""

    def __init__(self, config):
        """Initialize the data object."""
        from nokia import NokiaApi, NokiaCredentials
        credentials = NokiaCredentials(config.get("access_token"),
                                       config.get("access_token_secret"),
                                       config.get("consumer_key"),
                                       config.get("consumer_secret"),
                                       config.get("user_id"))
        self._api = NokiaApi(credentials)
        self.data = None
        self._update()

    @Throttle(SCAN_INTERVAL)
    def _update(self):
        """Get the latest data from Nokia Health."""
        self.data = self._api.get_measures(limit=1)
