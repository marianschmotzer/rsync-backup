#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Import smtplib for the actual sending function
import smtplib

# Import the email modules we'll need
from email.mime.text import MIMEText
from tqdm import tqdm
import argparse
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import string
import random
import datetime
import shutil

class BackupErrorException(Exception):
    pass

class DeleteErrorException(Exception):
    pass

class DelayedKeyboardInterrupt(object):
    """
    With this class is it possible to have code blocks, which can't be
    interrupted by SIGINT signal (eg. when pressing CTRL-C). If SIGINT
    was received, it will be released again on the exit of that block.

    Example:
    --------
    with DelayedKeyboardInterrupt():
        do_some()
        crucial()
        stuff()
    this_may_not_run_anymore()

    """

    def __init__(self, output=None):
        """
        Create DelayedKeyboardInterrupt to have code blocks uninterrupted by
        SIGINT signals.

        :param output: Optional instance of Output() to log debug message.
        """
        self.output = output

    def __enter__(self):
        self.signal_received = False
        self.old_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self.handler)

    def handler(self, sig, frame):
        self.signal_received = (sig, frame)
        if self.output:
            self.output.debug("received SIGINT and postpone it")

    def __exit__(self, type, value, traceback):
        signal.signal(signal.SIGINT, self.old_handler)
        if self.signal_received:
            if self.output:
                self.output.debug("release previousely reveived SIGINT")
            self.old_handler(*self.signal_received)


class Output(object):

    def __init__(self, debug=False, quiet=False):
        """
        Create a Output object to print console messages and a progress bar

        :param debug: Print debug messages.
        :param quiet: Don't be so verbose and show only errors.
        """
        self.debugging = debug
        self.bequiet = quiet
        self.tqdm = tqdm(disable=True)

    def debug(self, message):
        """
        Print a debug messages. If parameter debug was set to false or quiet
        was set to true, those messages will not be shown.
        """
        if not self.bequiet and self.debugging:
		self.tqdm.write(datetime.datetime.utcnow().isoformat() + " DEBUG: "  + message)

    def info(self, message):
        """
        Print a info messages. If parameter quiet was set to true, those
        message will not be shown.
        """
        if not self.bequiet:
		self.tqdm.write(datetime.datetime.utcnow().isoformat() + " INFO: "+  message)

    def error(self, message):
        """
        Print a error messages. Those message will regardless of what debug
        and quiet parameters was set.
        """
        if not self.bequiet:
            self.tqdm.write(datetime.datetime.utcnow().isoformat() + "ERROR: " + message)

    def pbar(self, total):
        """
        Show a progress bar where total is the amount of items which will
        be processed. The progress can be updated with the update() method.
        """
        if not self.bequiet and sys.stdout.isatty():
            self.tqdm = tqdm(total=total)

    def update(self, n):
        """
        Update the progress bar by say that n items have been processed since
        last call of update.
        """
        self.tqdm.update(n)

    def close(self):
        """
        Close the progress bar.
        """
        self.tqdm.close()


class DiskBackup(object):

    def __init__(self,directories_to_backup=['/srv'],mount_point=None, 
            targetdir='/mnt/backup',emails=None,keep_backups=3,smtp_server='localhost',mail_from='root'):
        """
        Create DiskBackup object which back up list of given reposietoris.
        existing database with database with a referenc in the mastercloud.

        :param directories_to_backup: list of directories to rsync to targetdir
        :param mount_point: Mount point of external disk
        :param targetdir: Path where data will be saved to.
        :param keep_backups: Number of backups to keep
        """
        self.targetdir = os.path.abspath(targetdir)
        self.keep_backups = keep_backups
        self.backupdir = os.path.join(os.path.abspath(targetdir),"%s" % time.strftime("%Y%m%d"))
        self.dbcons = {}
        self.output = Output()
        self.directories_to_backup = directories_to_backup
        self.mount_point = mount_point
        self.smtp_server = smtp_server
        self.mail_from = mail_from
        self.emails = emails

    def SendEmail(self,message):
        if self.emails :
            msg = MIMEText("Hi, \n %s \nYour backup script" % message)
            msg['Subject'] = message
            msg['From'] = self.mail_from
            msg['To'] = self.emails
            s = smtplib.SMTP(self.smtp_server)
            s.sendmail(self.mail_from,[self.emails], msg.as_string())
            s.quit()


    def RemoveOldBackup(self,targetdir,keep_backups):
        i=0
        directories=os.listdir(targetdir)

        directories.sort(key=lambda x: os.path.getmtime(os.path.join(targetdir,x)),reverse=True)
        if len(directories) < keep_backups:
            self.output.info("Not removing any old backup, number of backups %s" % len(directories))
            return 0
        else:
           i=keep_backups - 1
           while i < len(directories):
               self.output.info("Removing directory %s" % directories[i])
               shutil.rmtree(os.path.join(targetdir,directories[i]))
               i += 1
        return 0

    def BackupDir(self, directory, backupdir):
        """
        Backup the given database.
        :param database: Name of database to backup.
        :param server: Database server connection info.
        """
        self.output.info("backing up directory %s to %s" % (directory, backupdir))

        rsync_cmd = "rsync -rav {0} {1}/" \
                        .format(directory,backupdir)
        rsync_proc = subprocess.Popen(shlex.split(rsync_cmd),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        stdout = rsync_proc.stdout.read()
        if rsync_proc.wait() != 0:
            raise BackupErrorException("Creating backup failed for directory %s: %s" % (backupdir,stdout) )
        return 0
        self.output.info("Directory %s sucessfuly stored \
                          List of files transfered %s" % (directory,stdout))

    def run(self):
        """Main method to execute all the things."""
        i = 0
        if self.mount_point :
            self.output.info("Check if %s is mounted" % self.mount_point)
            if os.path.ismount(self.mount_point):
                self.output.info("Disk mounted at %s, backups continues" % self.mount_point)
                self.SendEmail("Disk mounted backup starts")
            else:
                try:
                    subprocess.check_call(["mount", self.mount_point])
                except Exception as e:
                    self.output.error("Disk not mounted and cannot be mounted because %s " % str(e))
                    self.SendEmail("Disk not attached please attach it! Reason %s" % str(e))
                    return 1
                self.output.info("Disk mounted at %s, backups continues" % self.mount_point)
                self.SendEmail("Disk mounted backup starts")

        try:
            if not os.path.exists(self.targetdir):
                os.makedirs(self.targetdir)

            """Backup directories"""
            for directory in self.directories_to_backup:
	        try:
                    self.BackupDir(directory,self.backupdir)
                except Exception as e:
                    self.output.error(str(e))
	        finally:
                    self.output.info("Backup was sucessfull")
        except Exception as e:
            self.output.error(str(e))
            self.SendEmail("Error %s, backup not sucessful" % str(e))
        finally:
            try:
                self.RemoveOldBackup(self.targetdir,self.keep_backups)
                if self.mount_point:
                    if os.path.ismount(self.mount_point):
                        subprocess.check_call(["umount", self.mount_point])
            except Exception as e:
                self.output.error(str(e))
                self.SendEmail("Error %s, backup not sucessful" % str(e))
            finally:
                self.SendEmail("Backup was sucessful ! You can remove disk")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(fromfile_prefix_chars='@',
        description="Backup directoris which are listed and remove old backups.",
        epilog="All parameters can be stored to a file in --param=value format, "
                + "one parameter per line, then specify this file with @file.")

    parser.add_argument("-d", "--directory", metavar="DIRECTORYLIST",
                        dest="directories_to_backup",action="append",
                        help="List of directories to backup." \
                              + "Can be specified multiple times. " )
    parser.add_argument("-t", "--targetdir", metavar="DIRECTORY", dest="targetdir",
                        help="Backup target directory")
    parser.add_argument("-m", "--mountpoint", metavar="DIRECTORY",dest="mount_point",
                        help="Mount point must be mounted befor backup")
    parser.add_argument("-k", "--keepbackups", metavar="KEEPBACKUPS",default=4,dest="keep_backups",
                        type=int,
                        help="Number of backups to keep")
    parser.add_argument("-e", "--email", metavar="EMAIL", dest="emails",
                        help="Email to send notifications to. " \
                              + "Can be specified multiple times. " )
    parser.add_argument("-f", "--from", metavar="EMAIL", dest="mail_from",
                        help="Email sender address. " \
                              + "no meaning without --email " )

    parser.add_argument("-s", "--smtpserver", metavar="SMTPSERVER",dest="smtp_server",
                        help="SMTP server to use " )

    args = vars(parser.parse_args())
    DiskBackup(**args).run()

