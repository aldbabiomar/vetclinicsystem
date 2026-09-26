"""The queries and calculations, one module per area of the clinic.

Nothing here imports Flask beyond flask_babel (translation): these run in
request threads, background jobs and the scheduler alike, and the request
layer (vcs/web) is the one that knows about requests.
"""
