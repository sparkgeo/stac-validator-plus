In this directory we have some boilerplate code for a STAC validator. I have similar working code in `../eodh-validator/` and `../claude-stac-validator`. The aim is to combine the functionality of these projects to get the best of both worlds: traditional Python and LLMs.

Broadly speaking, the flow should look like this:
User provides a STAC Item --> Python code is executed to validate the Item --> The output of that is passed to Claude along with the Item to catch other validation/compliance issues --> The final output is then formatted into a Markdown report.

I want you to interrogate me about how I see the application working. Keep asking questions until we both agree the project is well defined or until I tell you to stop. Ask one question at a time: multiple questions are confusing. We are just planning here, so no need to generate any code. If a question can be answered by looking at existing code, do that instead. Make suggestions about design patterns and best practices.

You can also use the STAC specification, best practices, and extensions documentation if you think it is appropriate.

The output will be an actionable design document in Markdown format.
