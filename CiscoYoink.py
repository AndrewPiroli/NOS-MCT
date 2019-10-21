#Andrew Piroli (c)2019
#  MIT LICENSE  #
from netmiko import ConnectHandler
import os
import datetime as time
import shutil
from threading import Thread
from SimpleConfigParse import SimpleConfigParse
class CiscoYoink(Thread):
	host, username, password = None, None, None
	connection = None
	shows = ["show run", "show run all", "show vlan", "show vlan brief", "show vtp status", "show vtp password", "show start", "show int trunk", "show version"]
	def __init__(self, host, username, password):
		super().__init__()
		self.host = host
		self.username = username
		self.password = password
	def cisco_connect(self, ip, username, password):
		device = { 
		'device_type': 'cisco_ios', 
		'host': ip, 
		'username': username, 
		'password': password, 
		}
		self.connection = ConnectHandler(**device)
	def run(self):
		self.cisco_connect(self.host, self.username, self.password)
		hostname = self.connection.find_prompt().split("#")[0]
		for show in self.shows:
			filename = hostname + "_" + (show.replace(" ", "_") + ".txt")
			try:
				with open(filename, "w") as show_file:
					show_file.write(self.connection.send_command(show))
				with open("ciscoyoink_helper.log", "a") as log:
					log.write(f"{hostname} {filename} epic_and_cool\n")
			except Exception as e:
				print(f"Error writing show for {hostname}!")
class CiscoYoinkHelper():
	self_help_book = []
	filename = None
	def __init__(self, file="ciscoyoink_helper.log"):
		self.filename = file
		librarian = SimpleConfigParse(file)
		self.self_help_book = librarian.read()
	def set_dir(self, name):
		try:
			os.mkdir(name)
		except FileExistsError:
			pass
		os.chdir(name) 
	def organize(self):
		original_dir = os.getcwd()
		for chapter in self.self_help_book:
			try:
				destination = chapter[1].replace(chapter[0] + "_", "")
				self.set_dir(chapter[0])
				shutil.move(f"../{chapter[1]}", f"./{destination}")
			except Exception:
				print(e)
				os.chdir(original_dir)
				continue
			finally:
				os.chdir(original_dir)
		os.remove(self.filename)
if __name__ == "__main__":
	NUM_THREADS_MAX = 10
	start = time.datetime.now()
	config = SimpleConfigParse("sample.config").read()
	threadlist= []
	for entry in config:
		threadlist.append(CiscoYoink(entry[0], entry[1], entry[2]))#### TODO: Better threading mechanism...
	while len(threadlist) > 0:
		for thread in threadlist[:NUM_THREADS_MAX]:
			thread.start()
		for thread in threadlist[:NUM_THREADS_MAX]:
			thread.join()
		threadlist = threadlist[NUM_THREADS_MAX:]
	CiscoYoinkHelper().organize()
	end = time.datetime.now()
	elapsed = (end-start).total_seconds()
	print(f"Time Elapsed: {elapsed}")
