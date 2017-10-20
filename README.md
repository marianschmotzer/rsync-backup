rsync-backup
-------------
Python file backup script with functionality:
* Sending email notifications
* Keeping only given number of backups
* Mounting/unmounting disk if it is mountpoint 
* Some more on the way

Parameters
--------------
# `-d, --directory`  List of directories to backup.Can be specified multiple times.  
# `-t, --targetdir` Backup target directory
# `-m, --mountpoint` Mount point must be mounted befor backup
# `-k, --keepbackups`  Number of backups to keep
# `-e, --email` Email to send notifications to.  
# `-f, --from` Email sender address.No meaning without --email  
# `-s, --smtpserver`  SMTP server to use  

Example of config file
-----------------------
```python
--directory=/srv/mail
--directory=/srv/samba
--directory=/srv/postgresql
--targetdir=/mnt/backup/
--email=admin
--smtpserver=localhost:25
--mountpoint=/mnt/backup
```
## Dependencies

Python modules : 
* tqdm
