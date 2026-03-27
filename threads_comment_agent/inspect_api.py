#!/usr/bin/env python3
"""Inspect threads_api package structure"""

try:
    import threads_api
    import inspect

    print("=" * 60)
    print("THREADS_API PACKAGE INSPECTION")
    print("=" * 60)

    # Show all public items
    print("\n📦 Available classes and functions:")
    items = [x for x in dir(threads_api) if not x.startswith('_')]
    for item in items:
        obj = getattr(threads_api, item)
        obj_type = type(obj).__name__
        print(f"  • {item} ({obj_type})")

    # Try to find ThreadsAPI
    print("\n🔍 Looking for ThreadsAPI class...")
    if hasattr(threads_api, 'ThreadsAPI'):
        print("✅ Found: threads_api.ThreadsAPI")
        api_class = threads_api.ThreadsAPI
        print(f"\nThreadsAPI methods:")
        methods = [m for m in dir(api_class) if not m.startswith('_')]
        for method in methods[:10]:
            print(f"  • {method}")
    else:
        print("❌ ThreadsAPI not found at top level")

        # Check submodules
        print("\n📂 Checking submodules...")
        import os
        pkg_path = threads_api.__path__[0]
        files = os.listdir(pkg_path)
        py_files = [f for f in files if f.endswith('.py')]
        print(f"Python files in {pkg_path}:")
        for f in py_files:
            print(f"  • {f}")

    print("\n" + "=" * 60)

except ImportError as e:
    print(f"❌ Cannot import threads_api: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
