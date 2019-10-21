#Andrew Piroli (c)2019
#  MIT LICENSE  #
class SimpleConfigParse():
	file = None
	contents = None
	def __init__(self, file):
		self.file = file
	def open(self):
		try:
			with open(self.file, "r") as config:
				self.contents = config.readlines()
		except Exception as e:
			print("Error opening config file!")
			print(e)
	def read(self):
		results = []
		self.open()
		for index, line in enumerate(self.contents):
			if line.startswith("#"):
				continue
			line = line.split(" ")
			try:
				results.append([line[0],line[1],line[2].strip()])
			except IndexError as e:
				print(f"Config file format error! - skipping entry on line: {index+1}")
				continue
		return results
