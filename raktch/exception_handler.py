"""
Custom DRF exception handler that returns structured validation errors.
All error responses follow the shape:
  { "detail": "...", "errors": {...} }
"""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return response

    data = response.data

    # Normalise into a consistent shape
    if isinstance(data, dict):
        if 'detail' not in data:
            # Validation errors: move field errors under 'errors'
            response.data = {
                'detail': 'Validation error.',
                'errors': data,
            }
    elif isinstance(data, list):
        response.data = {
            'detail': 'Validation error.',
            'errors': {'non_field_errors': data},
        }
    else:
        response.data = {'detail': str(data)}

    return response
