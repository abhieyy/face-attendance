bind = "0.0.0.0:10000"
workers = 1
worker_class = "eventlet"
timeout = 120

# Security settings
limit_request_line = 4094  # Limit request line size
limit_request_fields = 100  # Limit number of header fields
limit_request_field_size = 8190  # Limit header field sizes