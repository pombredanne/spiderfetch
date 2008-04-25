#!/usr/bin/env ruby
#
# Author: Martin Matusiak <numerodix@gmail.com>
# Licensed under the GNU Public License, version 3.


require "ftools"
require "optparse"
require "tempfile"
require "uri"

$program_name = File.basename __FILE__
$program_path = File.dirname __FILE__

$protocol_filter = /^[a-zA-Z]+:\/\//
$pattern = /.*/
$dump_urls = false
$dump_index = false
$dump_color = false

$colors = [:black, :red, :green, :yellow, :blue, :magenta, :cyan, :white]

$wget_tries = 44
$wget_ua = '--user-agent ""'  # work around picky hosts


in_tag = /<[^>]+?(?:[hH][rR][eE][fF]|[sS][rR][cC])[ ]*=?[ ]*(["'`])(.*?)\1[^>]*?>/m
uri_match = /[A-Za-z][A-Za-z0-9+.-]{1,120}:\/\/(([A-Za-z0-9$_.+!*,;\/?:@&~(){}\[\]=-])|%[A-Fa-f0-9]{2}){1,333}(#([a-zA-Z0-9][a-zA-Z0-9 $_.+!*,;\/?:@&~(){}\[\]=%-]{0,1000}))?/m

$regexs = [ 
	{:regex=>in_tag, :group=>2},
	{:regex=>uri_match, :group=>0},
	{:regex=>URI::regexp, :group=>0},
][0..5]	  # we only have 6 colors, let's not crash from array out of bounds


## parse args
opts = OptionParser.new do |opts|
	opts.banner = "Usage:  #{$program_name} <url> [<pattern>] [options]\n\n"

	opts.on("--useindex index_page", "Use this index instead of fetching") do |v|
		$index_file = v
	end
	opts.on("--recipe recipe", "Use this spidering recipe") do |v|
		$recipe_file = v
	end
	opts.on("--dump", "Dump urls, don't fetch") do |v|
		$dump_urls = true
	end
	opts.on("--dumpindex", "Dump index page") do |v|
		$dump_index = true
	end
	opts.on("--dumpcolor", "Dump index page formatted to show matches") do |v|
		$dump_color = true
	end
end 
opts.parse!

if ARGV.empty? and !$index_file
	puts opts.help
	exit 1
else
	$url = ARGV[0]
	ARGV.length > 1 and $pattern = Regexp.compile(ARGV[1])
end


## function to colorize output 
def color c, s, *opt
	col_num = $colors.index(c)
	if ENV['TERM'] == "dumb" 
		return s
	else
		b="0"
		opt and opt[0] and opt[0][:bold] and b="1"
		return "\e[#{b};3#{col_num}m#{s}\e[0m"
	end
end

def color_code c, code, *opt
	s = color(c, "z", *opt)
	if code and code == -1
		return Regexp.new("^(.*)z").match(s)[1].to_s
	elsif code == 1
		return Regexp.new("z(.*)$").match(s)[1].to_s
	end
end

## function to fetch with wget
def wget url, getdata, verbose
	begin
		pre_output = color(:yellow, "\nFetching url #{color(:cyan, url)}... ")
		ok_output = color(:yellow, "===> ") + color(:green, "DONE")
		err_output = color(:yellow, "===> ") + color(:red, "FAILED")

		# build execution string
		if !verbose
			logfile = Tempfile.new $program_name
			logto = "-o #{logfile.path}"
		end
		if getdata
			savefile = Tempfile.new $program_name
			saveto = "-O #{savefile.path}"
		end
		cert = "--no-check-certificate"
		cmd = "wget #{$wget_ua} #{cert} -k -c -t#{$wget_tries} #{logto} #{saveto} #{url}"

		# run command
		verbose and puts pre_output
		system(cmd)

		# handle exit value
		if $?.to_i > 0
			# noisy mode
			verbose and puts "\n\n#{err_output}, cmd was:\n#{cmd}"

			# quiet mode
			!verbose and output = "\n" + logfile.open.read
			raise Exception, 
				"#{pre_output}\n#{output}\n#{err_output}, cmd was:\n#{cmd}"
		else
			# noisy mode
			verbose and puts ok_output
		end
		getdata and return savefile.open.read
	ensure
		logfile and logfile.close!
		savefile and savefile.close!
	end
end

def fetch_url url, read_file, verbose
	begin
		content = wget url, read_file, verbose
	rescue Exception => e
		puts e.to_s
		exit 1
	end
	return content
end

def fetch_index url
	return fetch_url(url, true, false)
end

def fetch_file url
	return fetch_url(url, false, true)
end

def findall regex, group, s, pattern_filter
	cs = 0

	matches = []
	while m = regex.match(s[cs..-1])

		match_start = cs + m.begin(group)
		match_end = cs + m.end(group)

		if pattern_filter.match m[group] and $protocol_filter.match m[group]
			matches << {:start=>match_start, :end=>match_end}
		end

		cs = match_end
	end

	return matches
end

def format markers, s
	markers.empty? and return color(:white, s)

	sf = ""

	stack = []
	cursor = 0
	markers.each do |marker|
		orig_sym = marker[:color] != nil ? -1 : 1

		sym = orig_sym
		col = marker[:color]
		col_bold = false

		if orig_sym == -1 and stack.length > 0   # adding color on top of color
			col_bold = true
		elsif orig_sym == 1 and stack.length > 1   # ending color with color below
			col = stack[stack.length-2]
			sym = -1
			stack.length > 2 and col_bold = true   # two or more layers, make it bold
		end

		orig_sym == -1 and stack << marker[:color]
		orig_sym == 1 and stack.pop

		sf += s[cursor..marker[:marker]-1] + color_code(col, sym, {:bold=>col_bold})
		cursor = marker[:marker]
	end
	sf += s[markers[-1][:marker]..-1]	# write segment after last match
	return sf
end

def collect_find regexs, s, pattern_filter
	colors = [:green, :yellow, :cyan, :blue, :magenta, :red]

	matches = []
	regexs.each do |regex|
		ms = findall(regex[:regex], regex[:group], s, pattern_filter)
		ms = ms.each { |m| m[:color] = colors[regexs.index(regex)] ;
			m[:fallback] = regexs.index(regex) }   # extra sort parameter
		matches += ms
	end
	# sort to get longest match first, to wrap coloring around shorter
	matches.sort! { |m1, m2| 
		[m1[:start],m2[:end],m2[:fallback]] <=> 
		[m2[:start],m1[:end],m1[:fallback]] }

	urls = []
	matches.each do |match|
		urls << s[match[:start]..match[:end]-1]
	end

	markers = []
	matches.each do |match|
		markers << {:marker=>match[:start], :color=>match[:color], 
			:serial=>matches.index(match)}   # for later sorting by longest match
		markers << {:marker=>match[:end], :serial=>matches.index(match)}
	end
	markers.sort! { |m1, m2| [m1[:marker],m1[:serial]] <=> [m2[:marker],m2[:serial]] }
	formatted = format(markers, s)

	return {:matches=>matches, :urls=>urls, :formatted=>formatted}
end

def load_recipe path
	begin
		require "#{$program_path}/#{path}"
		return Recipe::RECIPE
	rescue Exception => e
		puts color(:red, "ERROR::") + "  Failed to load recipe #{path}"
		puts e.to_s, e.backtrace
		exit 1
	end
end



recipe = load_recipe $recipe_file if $recipe_file

## fetch url
if $index_file
	content = IO.read $index_file
else
	content = fetch_index $url
end

findings = collect_find($regexs, content, $pattern)
urls = findings[:urls].uniq.each { |u| u.split("\n").join("") }
formatted = findings[:formatted]

if $dump_color 
	puts formatted
	exit 0
elsif $dump_index 
	puts content
	exit 0
elsif $dump_urls 
	puts urls
	exit 0
end

## fetch individual urls
urls.each do |url|
	fetch_file url
end

