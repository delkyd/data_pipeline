# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals

from optparse import OptionGroup

from yelp_batch import Batch
from yelp_batch.batch import batch_command_line_options
from yelp_servlib.config_util import load_package_config

from data_pipeline.schematizer_clientlib.models.refresh import Priority
from data_pipeline.schematizer_clientlib.schematizer import get_schematizer


class FullRefreshJob(Batch):
    """
    FullRefreshJob parses command line arguments specifying full refresh jobs
    and registers the refresh jobs with the Schematizer.
    """

    def __init__(self):
        super(FullRefreshJob, self).__init__()
        self.notify_emails = ['bam+batch@yelp.com']

    @batch_command_line_options
    def define_options(self, option_parser):
        opt_group = OptionGroup(option_parser, 'Refresh Job Options')

        opt_group.add_option(
            '--source-id',
            dest='source_id',
            type='int',
            help='Source id of table to be refreshed.'
        )
        opt_group.add_option(
            '--offset',
            dest='offset',
            type='int',
            default=0,
            help='Row offset to start refreshing from. '
                 '(default: %default)'
        )
        opt_group.add_option(
            '--batch-size',
            dest='batch_size',
            type='int',
            default=500,
            help='Number of rows to process between commits '
                 '(default: %default).'
        )
        opt_group.add_option(
            '--priority',
            dest='priority',
            default='MEDIUM',
            help='Priority of this refresh: LOW, MEDIUM, HIGH or MAX '
                 '(default: %default)'
        )
        opt_group.add_option(
            '--filter-condition',
            dest='filter_condition',
            help='Custom WHERE clause to specify which rows to refresh '
                 'Note: This option takes everything that would come '
                 'after the WHERE in a sql statement. '
                 'e.g: --where="country=\'CA\' AND city=\'Waterloo\'"'
        )
        opt_group.add_option(
            '--avg-rows-per-second-cap',
            help='Caps the throughput per second. Important since without any control for this '
            'the batch can cause signifigant pipeline delays. (default: %default)',
            type='int',
            default=None
        )
        opt_group.add_option(
            '--config-path',
            dest='config_path',
            type='str',
            default='/nail/srv/configs/data_pipeline_tools.yaml',
            help='Config path for Refresh Job (default: %default)'
        )
        return opt_group

    def process_commandline_options(self, args=None):
        super(FullRefreshJob, self).process_commandline_options(args=args)
        if (self.options.avg_rows_per_second_cap is not None and
                self.options.avg_rows_per_second_cap <= 0):
            raise ValueError("--avg-rows-per-second-cap must be greater than 0")
        if self.options.batch_size <= 0:
            raise ValueError("--batch-size option must be greater than 0.")
        if self.options.source_id is None:
            raise ValueError("--source-id must be defined")

        load_package_config(self.options.config_path)
        self.schematizer = get_schematizer()

    def run(self):
        self.job = self.schematizer.create_refresh(
            source_id=self.options.source_id,
            offset=self.options.offset,
            batch_size=self.options.batch_size,
            priority=Priority[self.options.priority],
            filter_condition=self.options.filter_condition,
            avg_rows_per_second_cap=self.options.avg_rows_per_second_cap
        )
        self.log.info(
            "Refresh registered with refresh id: {rid} "
            "on source id: {sid}".format(
                rid=self.job.refresh_id,
                sid=self.job.source.source_id
            )
        )


if __name__ == '__main__':
    FullRefreshJob().start()
