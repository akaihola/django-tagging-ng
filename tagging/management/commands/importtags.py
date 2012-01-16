import sys
from optparse import make_option

from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import (
    connections, transaction, DEFAULT_DB_ALIAS, IntegrityError)

from tagging.models import Tag, Synonym


class Command(BaseCommand):
    help = 'Imports tags and synonyms from plain-text files.'
    args = "tagfile [tagfile ...]"

    option_list = BaseCommand.option_list + (
        make_option(
            '--database',
            action='store',
            dest='database',
            default=DEFAULT_DB_ALIAS,
            help=('Nominates a specific database to load '
                  'tags into. Defaults to the "default" database.'),
            ),
        make_option(
            '--no-transactions',
            action='store_true',
            help=('Run the import without transactions. '
                  'Good for catching duplicates and other errors.')),
            )

    def handle(self, *tag_files, **options):
        using = options.get('database', DEFAULT_DB_ALIAS)

        connection = connections[using]
        self.style = no_style()

        verbosity = int(options.get('verbosity', 1))
        show_traceback = options.get('traceback', False)
        transactions = not options.get('no_transactions', False)

        # commit is a stealth option - it isn't really useful as
        # a command line option, but it can be useful when invoking
        # importtags from within another script.
        # If commit=True, importtags will use its own transaction;
        # if commit=False, the data load SQL will become part of
        # the transaction in place when importtags was invoked.
        commit = options.get('commit', True)

        # Keep a count of the installed tags and synonyms
        tag_count = 0
        synonym_count = 0

        # Get a cursor (even though we don't need one yet). This has
        # the side effect of initializing the test database (if
        # it isn't already initialized).
        cursor = connection.cursor()

        # Start transaction management. All tags and synonyms are installed in
        # a single transaction to ensure that all references are resolved.
        if transactions and commit:
            if verbosity > 0:
                print 'Entering transaction'
            transaction.commit_unless_managed(using=using)
            transaction.enter_transaction_management(using=using)

        for tag_file_path in tag_files:
            if verbosity > 0:
                print "Importing tags and synonyms from %s." % tag_file_path
                print 'Using transactions: %r' % transactions
            tags_in_file = 0
            for line in open(tag_file_path):
                words = line.strip().decode('UTF-8').split()
                if not words:
                    continue
                if verbosity > 0:
                    print "Importing tag %r with synonyms %s." % (
                        words[0], ', '.join(repr(w) for w in words[1:]))
                tag_count += 1
                synonym_count += len(words)
                tags_in_file += 1
                try:
                    tag, created = Tag.objects.get_or_create(name=words[0])
                    for synonym in words:
                        Synonym.objects.get_or_create(name=synonym,
                                                      defaults={'tag': tag})
                except (SystemExit, KeyboardInterrupt):
                    raise
                except Exception:
                    import traceback
                    if transactions:
                        transaction.rollback(using=using)
                        transaction.leave_transaction_management(using=using)
                    if show_traceback:
                        traceback.print_exc()
                    else:
                        sys.stderr.write(self.style.ERROR(
                            "Problem adding tag %r: %s\n" % (
                                words[0],
                                ''.join(traceback.format_exception(
                                    sys.exc_type,
                                    sys.exc_value,
                                    sys.exc_traceback)))))
                    return

                # If the tag file we loaded contains 0 tags, assume that an
                # error was encountered during tag loading.
                if tags_in_file == 0:
                    sys.stderr.write(
                        self.style.ERROR("No tags found in %r. "
                                         "(File format may be invalid.)" %
                                         (tag_file_path)))
                    if transactions:
                        transaction.rollback(using=using)
                        transaction.leave_transaction_management(using=using)
                    return

        if transactions and commit:
            if verbosity > 0:
                print 'Commiting transaction'
            transaction.commit(using=using)
            transaction.leave_transaction_management(using=using)

        if tag_count == 0:
            if verbosity > 1:
                print "No tags found."
        else:
            if verbosity > 0:
                print "Installed %d tags and %d synonyms from %d file(s)" % (
                    tag_count, synonym_count, len(tag_files))

        # Close the DB connection. This is required as a workaround for an
        # edge case in MySQL: if the same connection is used to
        # create tables, load data, and query, the query can return
        # incorrect results. See Django #7572, MySQL #37735.
        if commit:
            connection.close()
