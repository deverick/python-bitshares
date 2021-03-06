from bitshares.instance import shared_bitshares_instance
from datetime import datetime, timedelta
import calendar
import dateutil.parser
from .utils import formatTimeFromNow, formatTime, formatTimeString
from .asset import Asset
from .amount import Amount
from .price import Price, Order, FilledOrder
from .account import Account
from .blockchain import Blockchain
from bitsharesbase import operations
from bitsharesbase.objects import Operation


class Market(dict):
    """ This class allows to easily access Markets on the blockchain for trading, etc.

        :param bitshares.bitshares.BitShares bitshares_instance: BitShares instance
        :param bitshares.asset.Asset base: Base asset
        :param bitshares.asset.Asset quote: Quote asset
        :returns: Blockchain Market
        :rtype: dictionary with overloaded methods

        Instances of this class are dictionaries that come with additional
        methods (see below) that allow dealing with a market and it's
        corresponding functions.

        This class tries to identify **two** assets as provided in the
        parameters in one of the following forms:

        * ``base`` and ``quote`` are valid assets (according to :class:`bitshares.asset.Asset`)
        * ``base:quote`` separated with ``:``
        * ``base/quote`` separated with ``/``
        * ``base-quote`` separated with ``-``

        .. note:: Throughout this library, the ``quote`` symbol will be
                  presented first (e.g. ``USD:BTS`` with ``USD`` being the
                  quote), while the ``base`` only refers to a secondary asset
                  for a trade. This means, if you call
                  :func:`bitshares.market.Market.sell` or
                  :func:`bitshares.market.Market.buy`, you will sell/buy **only
                  quote** and obtain/pay **only base**.

    """
    def __init__(
        self,
        *args,
        base=None,
        quote=None,
        bitshares_instance=None,
        **kwargs
    ):
        self.bitshares = bitshares_instance or shared_bitshares_instance()

        if len(args) == 1 and isinstance(args[0], str):
            import re
            quote_symbol, base_symbol = re.split("[/-:]", args[0])
            self.quote = Asset(quote_symbol, bitshares_instance=self.bitshares)
            self.base = Asset(base_symbol, bitshares_instance=self.bitshares)
            super(Market, self).__init__({"base": self.base, "quote": self.quote})
        if len(args) == 0 and base and quote:
            super(Market, self).__init__({"base": base, "quote": quote})
            self.base = base
            self.quote = quote

    def ticker(self):
        """ Returns the ticker for all markets.

            Output Parameters:

            * ``last``: Price of the order last filled
            * ``lowestAsk``: Price of the lowest ask
            * ``highestBid``: Price of the highest bid
            * ``baseVolume``: Volume of the base asset
            * ``quoteVolume``: Volume of the quote asset
            * ``percentChange``: 24h change percentage (in %)
            * ``settlement_price``: Settlement Price for borrow/settlement
            * ``core_exchange_rate``: Core exchange rate for payment of fee in non-BTS asset
            * ``price24h``: the price 24h ago

            Sample Output:

            .. code-block:: js

                {
                    {
                        "quoteVolume": 48328.73333,
                        "quoteSettlement_price": 332.3344827586207,
                        "lowestAsk": 340.0,
                        "baseVolume": 144.1862,
                        "percentChange": -1.9607843231354893,
                        "highestBid": 334.20000000000005,
                        "latest": 333.33333330133934,
                    }
                }

        """
        data = {}
        # Core Exchange rate
        data["core_exchange_rate"] = float(self["quote"]["options"]["core_exchange_rate"]["base"]["amount"])

        # smartcoin stuff
        if "bitasset_data_id" in self["quote"]:
            bitasset = self.bitshares.rpc.get_object(self["quote"]["bitasset_data_id"])
            backing_asset_id = bitasset["options"]["short_backing_asset"]
            if backing_asset_id == self["base"]["id"]:
                data["quoteSettlement_price"] = float(bitasset["current_feed"]["settlement_price"])
        elif "bitasset_data_id" in self["base"]:
            bitasset = self.bitshares.rpc.get_object(self["base"]["bitasset_data_id"])
            backing_asset_id = bitasset["options"]["short_backing_asset"]
            if backing_asset_id == self["quote"]["id"]:
                data["base_settlement_price"] = float(bitasset["current_feed"]["settlement_price"])

        ticker = self.bitshares.rpc.get_ticker(
            self["base"]["id"],
            self["quote"]["id"],
        )
        data["base_volume"] = float(ticker["base_volume"])
        data["quote_volume"] = float(ticker["quote_volume"])
        data["low"] = float(ticker["lowest_ask"])
        data["high"] = float(ticker["highest_bid"])
        data["last"] = float(ticker["latest"])
        data["percent_change"] = round(float(ticker["percent_change"]) * 100, 3)
        data["base_id"] = self["base"]["id"],
        data["base_symbol"] = self["base"]["symbol"]
        data["quote_id"] = self["quote"]["id"]
        data["quote_symbol"] = self["quote"]["symbol"]
        return data

    def volume24h(self):
        """ Returns the 24-hour volume for all markets, plus totals for primary currencies.

            Sample output:

            .. code-block:: js

                {
                    "BTS": 361666.63617,
                    "USD": 1087.0
                }

        """
        volume = self.bitshares.rpc.get_24_volume(
            self["base"]["id"],
            self["quote"]["id"],
        )
        return {
            self["base"]["symbol"]: float(volume["base_volume"]),
            self["quote"]["symbol"]: float(volume["quote_volume"])
        }

    def orderbook(self, limit=25):
        """ Returns the order book for a given market. You may also
            specify "all" to get the orderbooks of all markets.

            :param int limit: Limit the amount of orders (default: 25)

            Sample output:

            .. code-block:: js

                {'bids': [0.003679 USD/BTS (1.9103 USD|519.29602 BTS),
                0.003676 USD/BTS (299.9997 USD|81606.16394 BTS),
                0.003665 USD/BTS (288.4618 USD|78706.21881 BTS),
                0.003665 USD/BTS (3.5285 USD|962.74409 BTS),
                0.003665 USD/BTS (72.5474 USD|19794.41299 BTS)],
                'asks': [0.003738 USD/BTS (36.4715 USD|9756.17339 BTS),
                0.003738 USD/BTS (18.6915 USD|5000.00000 BTS),
                0.003742 USD/BTS (182.6881 USD|48820.22081 BTS),
                0.003772 USD/BTS (4.5200 USD|1198.14798 BTS),
                0.003799 USD/BTS (148.4975 USD|39086.59741 BTS)]}


            .. note:: Each bid is an instance of
                class:`bitshares.price.Order` and thus carries the keys
                ``base``, ``quote`` and ``price``. From those you can
                obtain the actual amounts for sale

        """
        orders = self.bitshares.rpc.get_order_book(
            self["base"]["id"],
            self["quote"]["id"],
            limit
        )
        _asks = [(float(elem["price"]), float(elem["quote"])) for elem in orders["asks"]]
        _bids = [(float(elem["price"]), float(elem["quote"])) for elem in orders["bids"]]
        data = {
            "asks": _asks,
            "bids": _bids,
            "base_id": self["base"]["id"],
            "base_symbol": self["base"]["symbol"],
            "quote_id": self["quote"]["id"],
            "quote_symbol": self["quote"]["symbol"]
        }
        return data

    def trades(self, limit=25, start=None, stop=None):
        """ Returns your trade history for a given market.

            :param int limit: Limit the amount of orders (default: 25)
            :param datetime start: start time
            :param datetime stop: stop time

        """
        # FIXME, this call should also return whether it was a buy or
        # sell
        if not stop:
            stop = datetime.now()
        if not start:
            start = stop - timedelta(hours=24)
        orders = self.bitshares.rpc.get_trade_history(
            self["base"]["symbol"],
            self["quote"]["symbol"],
            formatTime(stop),
            formatTime(start),
            limit)
        _trades = []
        for trade in orders:
            data = {}
            data["price"] = float(trade["price"])
            data["amount"] = float(trade["amount"])
            data["datetime"] = calendar.timegm(dateutil.parser.parse(trade["date"]).timetuple())
            _trades.append(data)
        data = {
            "trades": _trades,
            "base_id": self["base"]["id"],
            "base_symbol": self["base"]["symbol"],
            "quote_id": self["quote"]["id"],
            "quote_symbol": self["quote"]["symbol"]
        }
        return data

    def accounttrades(self, account=None, limit=25):
        """ Returns your trade history for a given market, specified by
            the "currencyPair" parameter. You may also specify "all" to
            get the orderbooks of all markets.

            :param str currencyPair: Return results for a particular market only (default: "all")
            :param int limit: Limit the amount of orders (default: 25)

            Output Parameters:

                - `type`: sell or buy
                - `rate`: price for `quote` denoted in `base` per `quote`
                - `amount`: amount of quote
                - `total`: amount of base at asked price (amount/price)

            .. note:: This call goes through the trade history and
                      searches for your account, if there are no orders
                      within ``limit`` trades, this call will return an
                      empty array.

        """
        if not account:
            if "default_account" in self.bitshares.config:
                account = self.bitshares.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, bitshares_instance=self.bitshares)

        filled = self.bitshares.rpc.get_fill_order_history(
            self["base"]["id"],
            self["quote"]["id"],
            2 * limit,
            api="history"
        )
        trades = []
        for f in filled:
            if f["op"]["account_id"] == account["id"]:
                trades.append(
                    FilledOrder(
                        f,
                        base=self["base"],
                        quote=self["quote"],
                        bitshares_instance=self.bitshares
                    ))
        return trades

    def accountopenorders(self, account=None):
        """ Returns open Orders

            :param bitshares.account.Account account: Account name or instance of Account to show orders for in this market
        """
        if not account:
            if "default_account" in self.bitshares.config:
                account = self.bitshares.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, full=True, bitshares_instance=self.bitshares)

        _orders = []
        orders = account["limit_orders"]
        for order in orders:
            if ((
                order["sell_price"]["base"]["asset_id"] == self["base"]["id"] and
                order["sell_price"]["quote"]["asset_id"] == self["quote"]["id"]
            ) or (
                order["sell_price"]["base"]["asset_id"] == self["quote"]["id"] and
                order["sell_price"]["quote"]["asset_id"] == self["base"]["id"]
            )):
                if order["sell_price"]["base"]["asset_id"] == self["base"]["id"]:
                    _base_amt = float(order["sell_price"]["base"]["amount"]) / 10 ** self.base.get("precision")
                    _quote_amt = float(order["sell_price"]["quote"]["amount"]) / 10 ** self.quote.get("precision")
                    _amount = _quote_amt
                    _price = _base_amt / _quote_amt

                else:
                    _base_amt = float(order["sell_price"]["base"]["amount"]) / 10 ** self.quote.get("precision")
                    _quote_amt = float(order["sell_price"]["quote"]["amount"]) / 10 ** self.base.get("precision")
                    _amount = _base_amt
                    _price = _quote_amt / _base_amt
                data = {}
                data["type"] = "buy" if order["sell_price"]["base"]["asset_id"] == self["base"]["id"] else "sell"
                data["price"] = _price
                data["amount"] = _amount 
                data["orderid"] = order["id"]
                data["status"] = "open"
                data["expiry_datetime"] = calendar.timegm(dateutil.parser.parse(order["expiration"]).timetuple())
                data["base_id"] = self["base"]["id"]
                data["base_symbol"] = self["base"]["symbol"]
                data["quote_id"] = self["quote"]["id"]
                data["quote_symbol"] = self["quote"]["symbol"]
                _orders.append(data)
        return _orders

    def buy(
        self,
        price,
        amount,
        expiration=7 * 24 * 60 * 60,
        killfill=False,
        account=None,
        returnOrderId=False
    ):
        """ Places a buy order in a given market

            :param float price: price denoted in ``base``/``quote``
            :param number amount: Amount of ``quote`` to buy
            :param number expiration: (optional) expiration time of the order in seconds (defaults to 7 days)
            :param bool killfill: flag that indicates if the order shall be killed if it is not filled (defaults to False)
            :param string account: Account name that executes that order
            :param string returnOrderId: If set to "head" or "irreversible" the call will wait for the tx to appear in
                                        the head/irreversible block and add the key "orderid" to the tx output

            Prices/Rates are denoted in 'base', i.e. the USD_BTS market
            is priced in BTS per USD.

            **Example:** in the USD_BTS market, a price of 300 means
            a USD is worth 300 BTS

            .. note::

                All prices returned are in the **reversed** orientation as the
                market. I.e. in the BTC/BTS market, prices are BTS per BTC.
                That way you can multiply prices with `1.05` to get a +5%.

            .. warning::

                Since buy orders are placed as
                limit-sell orders for the base asset,
                you may end up obtaining more of the
                buy asset than you placed the order
                for. Example:

                    * You place and order to buy 10 USD for 100 BTS/USD
                    * This means that you actually place a sell order for 1000 BTS in order to obtain **at least** 10 USD
                    * If an order on the market exists that sells USD for cheaper, you will end up with more than 10 USD
        """
        if not account:
            if "default_account" in self.bitshares.config:
                account = self.bitshares.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, bitshares_instance=self.bitshares)
        if isinstance(price, Price):
            if (
                price["quote"]["symbol"] == self["quote"]["symbol"] and
                price["base"]["symbol"] == self["base"]["symbol"]
            ):
                pass
            elif (
                price["base"]["symbol"] == self["quote"]["symbol"] and
                price["quote"]["symbol"] == self["base"]["symbol"]
            ):
                price = price.invert()
            else:
                raise ValueError("The assets in the price do not match the market!")

        if isinstance(amount, Amount):
            amount = Amount(amount, bitshares_instance=self.bitshares)
            assert(amount["asset"]["symbol"] == self["quote"]["symbol"])
        else:
            amount = Amount(amount, self["quote"]["symbol"], bitshares_instance=self.bitshares)

        order = operations.Limit_order_create(**{
            "fee": {"amount": 0, "asset_id": "1.3.0"},
            "seller": account["id"],
            "amount_to_sell": {
                "amount": int(float(amount) * float(price) * 10 ** self["base"]["precision"]),
                "asset_id": self["base"]["id"]
            },
            "min_to_receive": {
                "amount": int(float(amount) * 10 ** self["quote"]["precision"]),
                "asset_id": self["quote"]["id"]
            },
            "expiration": formatTimeFromNow(expiration),
            "fill_or_kill": killfill,
        })
        tx = self.bitshares.finalizeOp(order, account["name"], "active")
        if returnOrderId:
            chain = Blockchain(
                mode=("head" if returnOrderId == "head" else "irreversible"),
                bitshares_instance=self.bitshares
            )
            tx = chain.awaitTxConfirmation(tx)
            tx["orderid"] = tx["operation_results"][0][1]
        return tx

    def sell(
        self,
        price,
        amount,
        expiration=7 * 24 * 60 * 60,
        killfill=False,
        account=None,
        returnOrderId=False
    ):
        """ Places a sell order in a given market

            :param float price: price denoted in ``base``/``quote``
            :param number amount: Amount of ``quote`` to sell
            :param number expiration: (optional) expiration time of the order in seconds (defaults to 7 days)
            :param bool killfill: flag that indicates if the order shall be killed if it is not filled (defaults to False)
            :param string account: Account name that executes that order
            :param string returnOrderId: If set to "head" or "irreversible" the call will wait for the tx to appear in
                                        the head/irreversible block and add the key "orderid" to the tx output

            Prices/Rates are denoted in 'base', i.e. the USD_BTS market
            is priced in BTS per USD.

            **Example:** in the USD_BTS market, a price of 300 means
            a USD is worth 300 BTS

            .. note::

                All prices returned are in the **reversed** orientation as the
                market. I.e. in the BTC/BTS market, prices are BTS per BTC.
                That way you can multiply prices with `1.05` to get a +5%.
        """
        if not account:
            if "default_account" in self.bitshares.config:
                account = self.bitshares.config["default_account"]
        if not account:
            raise ValueError("You need to provide an account")
        account = Account(account, bitshares_instance=self.bitshares)
        if isinstance(price, Price):
            if (
                price["quote"]["symbol"] == self["quote"]["symbol"] and
                price["base"]["symbol"] == self["base"]["symbol"]
            ):
                pass
            elif (
                price["base"]["symbol"] == self["quote"]["symbol"] and
                price["quote"]["symbol"] == self["base"]["symbol"]
            ):
                price = price.invert()
            else:
                raise ValueError("The assets in the price do not match the market!")

        if isinstance(amount, Amount):
            amount = Amount(amount, bitshares_instance=self.bitshares)
            assert(amount["asset"]["symbol"] == self["quote"]["symbol"])
        else:
            amount = Amount(amount, self["quote"]["symbol"], bitshares_instance=self.bitshares)

        order = operations.Limit_order_create(**{
            "fee": {"amount": 0, "asset_id": "1.3.0"},
            "seller": account["id"],
            "amount_to_sell": {
                "amount": int(float(amount) * 10 ** self["quote"]["precision"]),
                "asset_id": self["quote"]["id"]
            },
            "min_to_receive": {
                "amount": int(float(amount) * float(price) * 10 ** self["base"]["precision"]),
                "asset_id": self["base"]["id"]
            },
            "expiration": formatTimeFromNow(expiration),
            "fill_or_kill": killfill,
        })
        tx = self.bitshares.finalizeOp(order, account["name"], "active")
        if returnOrderId:
            chain = Blockchain(
                mode=("head" if returnOrderId == "head" else "irreversible"),
                bitshares_instance=self.bitshares
            )
            tx = chain.awaitTxConfirmation(tx)
            tx["orderid"] = tx["operation_results"][0][1]
        return tx

    def cancel(self, orderNumber, account=None):
        """ Cancels an order you have placed in a given market. Requires
            only the "orderNumber". An order number takes the form
            ``1.7.xxx``.

            :param str orderNumber: The Order Object ide of the form ``1.7.xxxx``
        """
        return self.bitshares.cancel(orderNumber, account=account)
