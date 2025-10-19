
__all__ = []

def register_routes(app):
    if not __all__ :
        return
    
    blueprints = map(lambda bp: (eval(bp), '/'+bp.split('_')[0]), __all__)

    for blueprint, url_prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)

        