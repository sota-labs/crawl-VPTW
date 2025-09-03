import functools
import threading


def timeout(timeout=120):
    """
    A decorator that adds a timeout to a function execution.

    Args:
        timeout (int): The maximum time in seconds the function is allowed to run.

    Returns:
        A decorator function that wraps the original function.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            """
            The wrapper function that executes the original function with a timeout.

            Args:
                *args: Positional arguments to be passed to the original function.
                **kwargs: Keyword arguments to be passed to the original function.

            Returns:
                The result of the original function.

            Raises:
                TimeoutError: If the function execution takes longer than the specified timeout.  # noqa: E501
                Exception: Any exception raised by the original function.
            """

            def target():
                """
                The target function that executes the original function.

                Raises:
                    Exception: Any exception raised by the original function.
                """
                try:
                    wrapper.result = func(*args, **kwargs)
                except Exception as e:
                    print(f"Error within target function: {e}")
                    wrapper.exception = e
                    raise

            # Create and start the thread
            thread = threading.Thread(target=target)
            thread.start()

            try:
                # Join the thread with timeout
                thread.join(timeout)

                if thread.is_alive():
                    try:
                        thread._stop()  # Attempt to stop the thread gracefully
                    except Exception as e:
                        print(f"Error while stopping thread: {e}")
                    raise TimeoutError(
                        f"Function execution timed out after {timeout} seconds"
                    )
                else:
                    # Get the result from the thread
                    if hasattr(wrapper, "result"):
                        return wrapper.result
                    elif hasattr(wrapper, "exception"):
                        raise wrapper.exception
                    else:
                        raise RuntimeError(
                            "No result or exception found in the wrapper"
                        )
            except Exception as e:
                print(f"Error managing thread: {e}")
                raise

        return wrapper

    return decorator
