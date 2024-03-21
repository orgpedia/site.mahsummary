/**
 * Welcome to Cloudflare Workers! This is your first worker.
 *
 * - Run `npm run dev` in your terminal to start a development server
 * - Open a browser tab at http://localhost:8787/ to see your worker in action
 * - Run `npm run deploy` to publish your worker
 *
 * Learn more at https://developers.cloudflare.com/workers/
 */


async function create_subscriber(subs_name, email, list_id)
{
    // console.log('Inside create_subscriber')    
    const body_str = JSON.stringify({'email': email, 'name': subs_name, 'status': 'enabled', 'lists': [list_id]});

    const response = await fetch( listMonkAPIUrl + "/subscribers", {
	method: 'POST',
	headers: {
	    'Content-Type': 'application/json',
	    'authorization': 'Basic ' + listmonkKey,
	    'accept': '*/*'
	},
	body: body_str
    });
    const txt = await response.text();
    // console.log(txt);
    if (!response.ok)
    {
	throw new Error('Failed to create subscriber.');
    }
}


async function add_subscriber_tolist(subscriber_id, list_id)
{
    // console.log('add subscriber: ' + subscriber_id + " list_id: " + list_id)
    const body_str = JSON.stringify({'ids': [subscriber_id], 'action': 'add', 'target_list_ids': [list_id], 'status': 'confirmed'});
    
    const response = await fetch( listMonkAPIUrl + "/subscribers/lists", {
	method: 'PUT',
	headers: {
	    'Content-Type': 'application/json',
	    'authorization': 'Basic ' + listmonkKey,
	    'accept': '*/*'
	},
	body: body_str
    });
    
    const txt = await response.text();
    // console.log(txt);
    if (!response.ok)
    {
	throw new Error('Failed to create subscriber.');
    }
}

async function send_welcome_email(email, mailingList)
{
    const body_str = JSON.stringify({'subscriber_email': email, 'template_id': 4, 'data': {'list_name': mailingList}, 'content_type': 'html'});
    const response = await fetch( listMonkAPIUrl + "/tx", {
	method: 'POST',
	headers: {
	    'Content-Type': 'application/json;',
	    'authorization': 'Basic ' + listmonkKey,
	    'accept': '*/*'
	},
	body: body_str
    });
    
    const txt = await response.text();
    console.log(txt);
    if (!response.ok)
    {
	throw new Error('Failed to send welcome email.');
    }
}

export default {

    async fetch(request, env, ctx)
    {
	const url_string = await request.url;
	const url = new URL(url_string);
	const urlParams = new URLSearchParams(url.search);
	// console.log(url);

	const email = urlParams.get('emailInput');
	const name = urlParams.get('nameInput');
	const mailingList = urlParams.get('listNameForm');
	const list_id = parseInt(urlParams.get('listIDForm'));

	console.log('name: ' + name);
	console.log('email: ' + email);
	console.log('mailingList: ' + mailingList);
	console.log('list_id: ' + list_id);			

	if ( !email || !mailingList || !list_id) {
	    return new Response('Please provide Email, and Mailing List.', { status: 400 });
	}

	const person_name = name ? name : "No Name";

	try
	{
	    const subs_query  = encodeURIComponent(`subscribers.email='${email}'`).replace(/'/g, "%27");
	    const fetch_subscribers = `/subscribers?per_page=all&query=${subs_query}`;
	    // console.log(fetch_subscribers);
	    
	    const response = await fetch( listMonkAPIUrl + fetch_subscribers, {
		method: 'GET',
		headers: {
		    'Host': 'listsrv.orgpedia.in',
		    'authorization': 'Basic ' + listmonkKey,
		    'accept': '*/*'
		}
	    });
	    if (!response.ok)
	    {
		throw new Error('Failed to get subscriber information.');
	    }
	    const txt = await response.text();
	    // console.log(txt);	    
	    const parsedData = JSON.parse(txt);
	    if (parsedData.data.results.length == 0)
	    {
		await create_subscriber(person_name, email, list_id);
		await send_welcome_email(email, mailingList);
		return new Response(`Subscriber created and added to list ${mailingList}`);
	    }
	    else
	    {
		const subscribed_lists = parsedData.data.results.map(result => result.lists.map(list => list.id)).flat();
		if (subscribed_lists.includes(list_id))
		{
		    return new Response(`Subscriber ${email} exists in ${mailingList}`, {status: 200 });
		}
		else
		{
		    const subscriber_id = parseInt(parsedData.data.results[0]['id']);
		    await add_subscriber_tolist(subscriber_id, list_id);
		    await send_welcome_email(email, mailingList);		    
		    return new Response(`Added subscriber to ${mailingList}`, {status: 200});		    
		}
	    }
	}
	catch (error)
	{
	    // Handle any errors that occur during API invocations
	    return new Response('Error occurred while processing the request.' + error, { status: 500 })
	}	
	return new Response('Hello World!');
    },
};
