"""The Python worker: takes Python jobs from the queue and runs the stage handler registered for each.
What runs next is decided by the queue (pipeline_stages in the database), never here."""
