"""Guided tour walkthrough (architecture section 32): the guide agent reads the code in a read-only VM, plain code checks
its plan, and the driver shows each step on the live site while the page streams what is said.

    guide.py   reads the code with three fixed tools and writes the tour plan
    check.py   keeps only the sentences whose code proof exists, and the browser steps the safety rules allow
    driver.py  shows a step on the live site with the same runner the tests use, and judges nothing
    answer.py  does one chat message from start to finish
"""
