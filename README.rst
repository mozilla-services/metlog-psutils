=========
metlog-psutils
=========

metlog-psutils is a plugin extension for `Metlog 
<http://github.com/mozilla-services/metlog-py>`.  metlog-psutils adds
a `procinfo` method to the metlog client that is capable of capturing
details about network connections, memory usage, cpu usage and even
some thread details.

Configuration
=============

Usage
=====


Performance Considerations
==========================

out of process
needs access to subprocess
overriding noisy logging


The Metlog system consists of three pieces:

generator
  This is the application that will be generating the data that is to be sent
  into the system.

router
  This is the initial recipient of the messages that the generator will be
  sending. Typically, a metlog router deserializes the messages it receives,
  examines them, and decides based on the message metadata or contents which
  endpoint(s) to which the message should be delivered.

endpoints
  Different types of messages lend themselves to different types of
  presentation, processing, and analytics. The router has the ability to
  deliver messages of various types to destinations that are appropriate for
  handling those message types. For example, simple log messages might be
  output to a log file, while counter timer info is delivered to a `statsd
  <https://github.com/etsy/statsd>`_ server, and Python exception information
  is sent to a `Sentry <https://github.com/dcramer/sentry>`_ server.

The metlog-py library you are currently reading about is a client library meant
to be used by Python-based generator applications. It provides a means for
those apps to insert messages into the system for delivery to the router and,
ultimately, one or more endpoints.

More information about how Mozilla Services is using Metlog (including what is
being used for a router and what endpoints are in use / planning to be used)
can be found on the relevant `spec page
<https://wiki.mozilla.org/Services/Sagrada/Metlog>`_.
