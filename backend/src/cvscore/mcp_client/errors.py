class GatewayError(Exception):
    """The gateway cannot be reached or did not answer (network, timeout, protocol).

    Different from a tool that fails: that comes back as ToolResult(is_error=True)
    and the model can react to it. This one is an infrastructure problem.
    """
