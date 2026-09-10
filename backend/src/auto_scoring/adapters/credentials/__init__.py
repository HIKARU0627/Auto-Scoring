"""User-supplied API keys: where they are kept, how they reach the provider
chain, and how to find out whether one works (Issue #96).

* :mod:`store` -- the OS credential store, and what happens on a host with
  no usable backend.
* :mod:`api_keys` -- which providers take a key, and the layering that puts
  a stored key in front of the environment without touching `os.environ`.
* :mod:`verification` -- one real, unbilled call with the saved key.
"""
