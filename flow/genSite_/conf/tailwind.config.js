/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [".conf/templates/**/*.html"],
  theme: {
      extend: {
	  scale: {
	      '200': '2.00',
	  }
	  
      },
  },
  plugins: [],
}
