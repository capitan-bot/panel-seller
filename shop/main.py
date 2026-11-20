from __future__ import annotations

import os

from aiohttp import web

from web import app as A

from . import auth, buy, pages, wallet


def main():
    from . import theme
    auth.shell = theme.shell
    from . import skin
    from . import landing
    from . import unify
    app = web.Application(middlewares=[auth.guard])
    app.on_startup.append(buy.startup)
    auth.install(app)
    pages.install(app)
    buy.install(app)
    wallet.install(app)
    app.router.add_static("/static/", A.ASSETS)
    port = int(os.environ.get("SHOP_PORT", "8788"))
    print("shop listening on 127.0.0.1:%d" % port, flush=True)
    web.run_app(app, host=os.environ.get("SHOP_HOST", "127.0.0.1"), port=port, access_log=None, print=None)


if __name__ == "__main__":
    main()
