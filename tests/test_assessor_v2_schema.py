import json

from rq1.assessment_protocol import RUBRIC, contract, request_for, response_schema
from rq1.calibration import bank
from rq1.judge import validate_request


def test_public_format_matches_the_importers_existing_rules():
    schema = response_schema('packet-id')
    assert schema['properties']['adequacy']['enum'] == ['adequate', 'inadequate', 'uncertain']
    assert schema['properties']['review_id']['const'] == 'packet-id'
    assert schema['properties']['cited_lines']['items']['type'] == 'integer'
    premise = schema['properties']['premises']['items']
    assert premise['properties']['cited_lines']['minItems'] == 1
    assert schema['allOf'][0]['then']['properties']['relationships']['minItems'] == 1
    assert 'lowercase' in RUBRIC and 'integer source line numbers' in RUBRIC
    assert contract()['protocol_id'] == 'rq1-excerpt-v2'
    assert 'const' not in contract()['response_schema']['properties']['review_id']


def test_revised_requests_reproduce_without_private_case_oracle():
    packets, _ = bank()
    assert len(packets) == 12
    for packet in packets.values():
        request = request_for(packet, pass_id='calibration')
        assert validate_request(request) == packet
        body = json.loads(request['messages'][1]['content'])
        assert set(body) == {'task', 'response_schema'}
        assert set(body['task']) == {'review_id', 'claim', 'code', 'assessment_contract'}
        assert body['response_schema']['properties']['review_id']['const'] == packet['review_id']
        assert 'answer_key' not in request['messages'][1]['content']
