zone_occupancy = {"home": 0, "Irma-Wenke-Str": 0, "geretsried": 0}

for entity_id in hass.states.entity_ids('device_tracker'):
    if "ios" in entity_id:
        state = hass.states.get(entity_id)
        try:
            zone_occupancy[state.state] = zone_occupancy[state.state] + 1
        except KeyError as err:
            logger.debug("zone %s not counted" % state.state)

for zone, occupants in zone_occupancy.items():
    hass.states.set('sensor.occupants_' + zone.replace("-", "_"), occupants, {
                    'unit_of_measurement': None,
                    'friendly_name': 'Occupants ' + zone})
